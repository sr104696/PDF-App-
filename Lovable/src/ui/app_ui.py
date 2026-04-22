"""Tkinter UI: Library / Search / Tools tabs.

Long-running work (indexing, OCR, EPUB→PDF) runs on a worker thread and
posts progress back to the UI via a thread-safe queue polled by `after()`.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from . import dialogs, styles
from ..index import indexer
from ..index.migrations import open_db
from ..search import searcher
from ..core import pdf_parser, epub_parser
from ..utils.constants import APP_NAME, DB_PATH, DATA_DIR, SUPPORTED_EXTS


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.mode = "light"
        self.palette = styles.apply(root, self.mode)
        self.root.title(APP_NAME)
        self.root.geometry("1080x720")
        self.root.minsize(900, 600)

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = open_db(DB_PATH)

        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        self._build_topbar()
        self._build_tabs()
        self._refresh_library()

        self.root.after(80, self._drain_queue)
        self._enable_dnd()
        self._bind_shortcuts()

    # ---------- layout ----------------------------------------------------
    def _build_topbar(self):
        bar = ttk.Frame(self.root, padding=(14, 10))
        bar.pack(fill="x")
        ttk.Label(bar, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Button(bar, text="About", command=lambda: dialogs.about(self.root)).pack(side="right")
        ttk.Button(bar, text="Toggle Theme", command=self._toggle_theme).pack(side="right", padx=(0, 8))

    def _build_tabs(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._build_library_tab()
        self._build_search_tab()
        self._build_tools_tab()

    # ---------- LIBRARY ---------------------------------------------------
    def _build_library_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Library")

        actions = ttk.Frame(tab); actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Add Files…", command=self._pick_files).pack(side="left")
        ttk.Button(actions, text="Add Folder…", command=self._pick_folder).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Re-scan Library", command=self._rescan).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Remove Selected", command=self._remove_selected).pack(side="left", padx=(8, 0))

        self.lib_status = ttk.Label(actions, text="", style="Muted.TLabel")
        self.lib_status.pack(side="right")

        cols = ("title", "type", "pages", "tokens", "path")
        self.lib_tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="extended")
        for cid, label, w in (("title", "Title", 320), ("type", "Type", 60),
                              ("pages", "Pages", 70), ("tokens", "Tokens", 90),
                              ("path", "Path", 480)):
            self.lib_tree.heading(cid, text=label)
            self.lib_tree.column(cid, width=w, anchor="w")
        self.lib_tree.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(tab, mode="determinate")
        self.progress.pack(fill="x", pady=(10, 0))
        self.progress_label = ttk.Label(tab, text="", style="Muted.TLabel")
        self.progress_label.pack(anchor="w")

    # ---------- SEARCH ----------------------------------------------------
    def _build_search_tab(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text="Search")

        bar = ttk.Frame(tab); bar.pack(fill="x")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.search_var, font=("Segoe UI", 12))
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        entry.bind("<Return>", lambda _e: self._do_search())
        ttk.Button(bar, text="Search", style="Accent.TButton",
                   command=self._do_search).pack(side="left", padx=(8, 0))

        self.search_status = ttk.Label(tab, text="Tip: use \"quoted phrase\" for exact match. Press Ctrl+L to focus search.",
                                       style="Muted.TLabel")
        self.search_status.pack(anchor="w", pady=(6, 8))

        body = ttk.Frame(tab); body.pack(fill="both", expand=True)

        # Sidebar — facets + history
        side = ttk.Frame(body, width=220); side.pack(side="left", fill="y")
        ttk.Label(side, text="Filters", style="Heading.TLabel").pack(anchor="w")
        self.facet_box = tk.Listbox(side, height=10, exportselection=False,
                                    bg=self.palette["card"], fg=self.palette["fg"],
                                    bd=0, highlightthickness=0)
        self.facet_box.pack(fill="x", pady=(4, 12))
        self.facet_box.bind("<<ListboxSelect>>", lambda _e: self._do_search())

        ttk.Label(side, text="History", style="Heading.TLabel").pack(anchor="w")
        self.history_box = tk.Listbox(side, height=10,
                                      bg=self.palette["card"], fg=self.palette["fg"],
                                      bd=0, highlightthickness=0)
        self.history_box.pack(fill="both", expand=True, pady=(4, 0))
        self.history_box.bind("<Double-Button-1>", self._reuse_history)

        # Results panel
        right = ttk.Frame(body); right.pack(side="right", fill="both", expand=True, padx=(12, 0))
        self.results_canvas = tk.Canvas(right, bg=self.palette["bg"],
                                        highlightthickness=0)
        self.results_canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(right, orient="vertical", command=self.results_canvas.yview)
        scroll.pack(side="right", fill="y")
        self.results_canvas.configure(yscrollcommand=scroll.set)
        self.results_inner = ttk.Frame(self.results_canvas)
        self._results_window = self.results_canvas.create_window(
            (0, 0), window=self.results_inner, anchor="nw")
        self.results_inner.bind(
            "<Configure>",
            lambda _e: self.results_canvas.configure(
                scrollregion=self.results_canvas.bbox("all")))
        self.results_canvas.bind(
            "<Configure>",
            lambda e: self.results_canvas.itemconfigure(
                self._results_window, width=e.width))
        self.results_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.results_canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._refresh_history()

    # ---------- TOOLS -----------------------------------------------------
    def _build_tools_tab(self):
        tab = ttk.Frame(self.nb, padding=16)
        self.nb.add(tab, text="Tools")

        ocr_frame = ttk.Frame(tab); ocr_frame.pack(fill="x", pady=(0, 18))
        ttk.Label(ocr_frame, text="OCR (Make PDF Searchable)",
                  style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            ocr_frame,
            text=("Re-indexes a PDF using Tesseract OCR for scanned/image pages. "
                  "Requires Tesseract installed on your system (not bundled — keeps app small)."),
            style="Muted.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(2, 6))
        row = ttk.Frame(ocr_frame); row.pack(fill="x")
        self.ocr_btn = ttk.Button(row, text="OCR a PDF…", command=self._ocr_pick)
        self.ocr_btn.pack(side="left")
        status = "Tesseract: detected ✓" if pdf_parser.tesseract_available() else "Tesseract: not found ✗"
        ttk.Label(row, text=status, style="Muted.TLabel").pack(side="left", padx=(12, 0))

        epub_frame = ttk.Frame(tab); epub_frame.pack(fill="x")
        ttk.Label(epub_frame, text="EPUB → PDF", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(
            epub_frame,
            text="Convert an EPUB to a simple, searchable PDF. Pure-Python (reportlab).",
            style="Muted.TLabel", wraplength=900, justify="left",
        ).pack(anchor="w", pady=(2, 6))
        ttk.Button(epub_frame, text="Convert EPUB…", command=self._epub_pick).pack(anchor="w")

    # ---------- handlers --------------------------------------------------
    def _toggle_theme(self):
        self.mode = "dark" if self.mode == "light" else "light"
        self.palette = styles.apply(self.root, self.mode)
        # Recolour widgets that don't inherit ttk style.
        for box in (getattr(self, "facet_box", None),
                    getattr(self, "history_box", None)):
            if box:
                box.configure(bg=self.palette["card"], fg=self.palette["fg"])
        self.results_canvas.configure(bg=self.palette["bg"])

    def _bind_shortcuts(self):
        self.root.bind("<Control-l>", lambda _e: (self.nb.select(1), self._focus_search()))
        self.root.bind("<Control-o>", lambda _e: self._pick_files())
        self.root.bind("<F5>", lambda _e: self._rescan())

    def _focus_search(self):
        for w in self.nb.nametowidget(self.nb.tabs()[1]).winfo_children():
            for c in w.winfo_children():
                if isinstance(c, ttk.Entry):
                    c.focus_set()
                    return

    def _enable_dnd(self):
        # tkinterdnd2 is NOT a dep (size). We accept files dragged onto the window
        # via the simpler approach: a "drop text" hint + Ctrl+O / Add Files button.
        # On Windows, users can also right-click → "Open with" the app on a file.
        pass

    # ---- library actions
    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF / EPUB files",
            filetypes=[("Documents", "*.pdf *.epub"),
                       ("PDF", "*.pdf"), ("EPUB", "*.epub"), ("All", "*.*")],
        )
        if paths:
            self._start_indexing([Path(p) for p in paths])

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Add a folder to the library")
        if d:
            self._start_indexing([Path(d)])

    def _rescan(self):
        docs = indexer.list_documents(self.conn)
        paths = [Path(d["file_path"]) for d in docs if Path(d["file_path"]).exists()]
        if not paths:
            self.lib_status.configure(text="Nothing to re-scan.")
            return
        self._start_indexing(paths)

    def _remove_selected(self):
        sel = self.lib_tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Remove", f"Remove {len(sel)} document(s) from the index?"):
            return
        for iid in sel:
            try:
                indexer.remove_document(self.conn, int(iid))
            except Exception as e:
                messagebox.showerror("Remove failed", str(e))
        self._refresh_library()

    def _start_indexing(self, paths: list[Path]):
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("Busy", "An indexing job is already running.")
            return

        def work():
            def cb(msg, done, total):
                self._queue.put(("progress", msg, done, total))
            try:
                stats = indexer.index_paths(self.conn, paths, ocr=False, progress=cb)
                self._queue.put(("indexed_done", stats))
            except Exception as e:
                self._queue.put(("error", str(e)))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self.progress.configure(value=0, maximum=100)
        self.progress_label.configure(text="Starting…")

    def _refresh_library(self):
        for iid in self.lib_tree.get_children():
            self.lib_tree.delete(iid)
        docs = indexer.list_documents(self.conn)
        for d in docs:
            self.lib_tree.insert(
                "", "end", iid=str(d["id"]),
                values=(d["title"], d["file_type"].upper(),
                        d["page_count"], d["total_tokens"], d["file_path"]),
            )
        n_chunks, _avg = indexer.corpus_stats(self.conn)
        self.lib_status.configure(
            text=f"{len(docs)} document(s) · {n_chunks} chunks indexed")

    # ---- search
    def _do_search(self):
        q = self.search_var.get().strip()
        if not q:
            return
        filters = {}
        sel = self.facet_box.curselection()
        if sel:
            label = self.facet_box.get(sel[0])
            if ":" in label:
                key, val = label.split(":", 1)
                val = val.split("·")[0].strip()
                if key.strip() in {"file_type", "author", "year", "collection"}:
                    filters[key.strip()] = val

        try:
            resp = searcher.search(self.conn, q, filters=filters or None)
        except Exception as e:
            messagebox.showerror("Search error", str(e))
            return

        self.search_status.configure(
            text=f"{len(resp.results)} result(s) · {resp.elapsed_ms:.1f} ms")
        self._render_results(resp)
        self._render_facets(resp.facets)
        self._refresh_history()

    def _render_results(self, resp: searcher.SearchResponse):
        for w in self.results_inner.winfo_children():
            w.destroy()
        if not resp.results:
            ttk.Label(self.results_inner,
                      text="No matches. Try fewer or different keywords.",
                      style="Muted.TLabel").pack(anchor="w", padx=8, pady=12)
            return
        for r in resp.results:
            card = ttk.Frame(self.results_inner, style="Card.TFrame", padding=12)
            card.pack(fill="x", pady=6, padx=4)
            head = ttk.Frame(card, style="Card.TFrame"); head.pack(fill="x")
            ttk.Label(head,
                      text=f"{r.title}  ·  p.{r.page_num}"
                           + (f"  ·  {r.section}" if r.section else ""),
                      style="Heading.TLabel").pack(side="left", anchor="w")
            ttk.Label(head, text=f"score {r.score:.3f}",
                      style="Muted.TLabel").pack(side="right")

            ttk.Label(card, text=r.snippet, style="Snippet.TLabel",
                      justify="left").pack(anchor="w", pady=(6, 6))
            actions = ttk.Frame(card, style="Card.TFrame"); actions.pack(fill="x")
            ttk.Button(actions, text="Open file",
                       command=lambda p=r.file_path: self._open_file(p)).pack(side="left")
            ttk.Label(actions, text=r.file_path, style="Muted.TLabel").pack(side="left", padx=(10, 0))

    def _render_facets(self, facets):
        self.facet_box.delete(0, "end")
        for field, vals in facets.items():
            for v, c in vals:
                self.facet_box.insert("end", f"{field}: {v}  ·  {c}")

    def _refresh_history(self):
        self.history_box.delete(0, "end")
        for q in searcher.history(self.conn):
            self.history_box.insert("end", q)

    def _reuse_history(self, _e):
        sel = self.history_box.curselection()
        if sel:
            self.search_var.set(self.history_box.get(sel[0]))
            self._do_search()

    def _open_file(self, path: str):
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(Path(path).resolve().as_uri())
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    # ---- tools
    def _ocr_pick(self):
        path = filedialog.askopenfilename(
            title="Select a PDF to OCR",
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return
        if not pdf_parser.tesseract_available():
            messagebox.showwarning(
                "Tesseract missing",
                "Install Tesseract OCR and ensure it is on your PATH.\n"
                "Windows: https://github.com/UB-Mannheim/tesseract/wiki",
            )
            return

        def work():
            try:
                self._queue.put(("progress", f"OCR {Path(path).name}", 0, 1))
                indexer.index_file(self.conn, Path(path), ocr=True)
                indexer.rebuild_term_df(self.conn)
                self._queue.put(("indexed_done",
                                 {"total": 1, "indexed": 1, "skipped": 0, "failed": 0}))
            except Exception as e:
                self._queue.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _epub_pick(self):
        path = filedialog.askopenfilename(
            title="Select an EPUB",
            filetypes=[("EPUB", "*.epub")],
        )
        if not path:
            return
        out = filedialog.asksaveasfilename(
            title="Save PDF as", defaultextension=".pdf",
            initialfile=Path(path).with_suffix(".pdf").name,
            filetypes=[("PDF", "*.pdf")],
        )
        if not out:
            return

        def work():
            try:
                epub_parser.to_pdf(Path(path), Path(out))
                self._queue.put(("info", f"Wrote {out}"))
            except Exception as e:
                self._queue.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---- queue pump ------------------------------------------------------
    def _drain_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, label, done, total = msg
                    pct = 0 if total <= 0 else int(done * 100 / total)
                    self.progress.configure(value=pct, maximum=100)
                    self.progress_label.configure(text=f"{label}  ({done}/{total})")
                elif kind == "indexed_done":
                    _, stats = msg
                    self.progress.configure(value=100)
                    self.progress_label.configure(
                        text=(f"Done. indexed={stats['indexed']} "
                              f"skipped={stats['skipped']} failed={stats['failed']}"))
                    self._refresh_library()
                elif kind == "info":
                    messagebox.showinfo("Info", msg[1])
                elif kind == "error":
                    messagebox.showerror("Error", msg[1])
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def shutdown(self):
        try:
            self.conn.close()
        except Exception:
            pass


def run():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.shutdown(), root.destroy()))
    root.mainloop()
