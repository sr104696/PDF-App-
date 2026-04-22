"""Main application UI — three-tab Tkinter app.

Tabs:
  Library  — manage indexed files
  Search   — holistic query interface with intent display + expansion debug
  Tools    — OCR, EPUB conversion, embedding model setup

Threading model:
  All heavy work (indexing, searching) runs on a worker thread.
  Results are posted to a queue.Queue polled by root.after(50).
  UI is never frozen.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Dict, List, Optional

# Only constants are imported eagerly — they have zero heavy dependencies.
from ..utils.constants import (
    APP_NAME, APP_VERSION, DATA_DIR, SUPPORTED_EXTS,
)
from . import styles, dialogs

_POLL_MS = 50


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1100x720")
        self.minsize(800, 560)

        # Heavy modules loaded lazily on first use (see _get_* helpers below).
        self._indexer = None
        self._searcher = None
        self._conn = None
        self._embed_available_cache = None  # None = not yet checked

        self._queue: queue.Queue = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        self._style = ttk.Style(self)
        styles.apply(self, self._style)

        self._build_menu()
        self._build_notebook()
        self._build_status_bar()

        self.bind("<Control-f>", lambda e: self._focus_search())
        self.bind("<Control-o>", lambda e: self._add_files())
        self.bind("<Escape>",    lambda e: self._clear_search())

        self.after(_POLL_MS, self._poll_queue)

        # Show the window immediately, then load the heavy stuff in background.
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._status_var.set("Loading library…")
        threading.Thread(target=self._bg_init, daemon=True).start()

    # ── Lazy module accessors ────────────────────────────────────────────────

    def _get_conn(self):
        """Return DB connection, creating it if needed (always called from worker thread)."""
        if self._conn is None:
            from ..index.schema import get_connection
            self._conn = get_connection()
        return self._conn

    def _get_indexer(self):
        if self._indexer is None:
            from ..index import indexer as _ix
            self._indexer = _ix
        return self._indexer

    def _get_searcher(self):
        if self._searcher is None:
            from ..search import searcher as _sr
            self._searcher = _sr
        return self._searcher

    def _embed_available(self) -> bool:
        if self._embed_available_cache is None:
            try:
                from ..search.embeddings import is_available
                self._embed_available_cache = is_available()
            except Exception:
                self._embed_available_cache = False
        return self._embed_available_cache

    # ── Background init (runs in worker thread) ──────────────────────────────

    def _bg_init(self):
        """Load DB + check embeddings off the main thread so the window stays responsive."""
        try:
            conn = self._get_conn()  # initialises schema
            # Check embeddings availability and flip constant if needed.
            if self._embed_available():
                import src.utils.constants as c
                c.EMBEDDING_ENABLED = True
            self._queue.put(("init_done", conn))
        except Exception as e:
            self._queue.put(("error", f"Startup error: {e}"))

    # ── Menu ────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self)
        self.config(menu=mb)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="Add Files…   Ctrl+O", command=self._add_files)
        fm.add_command(label="Add Folder…",          command=self._add_folder)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.quit)
        mb.add_cascade(label="File", menu=fm)
        vm = tk.Menu(mb, tearoff=0)
        vm.add_command(label="Toggle Dark / Light Mode", command=self._toggle_theme)
        mb.add_cascade(label="View", menu=vm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="Embedding model setup…", command=self._show_embed_help)
        hm.add_command(label=f"About {APP_NAME}", command=self._show_about)
        mb.add_cascade(label="Help", menu=hm)

    # ── Notebook ────────────────────────────────────────────────────────────

    def _build_notebook(self):
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        self._build_library_tab()
        self._build_search_tab()
        self._build_tools_tab()

    # ── Library tab ─────────────────────────────────────────────────────────

    def _build_library_tab(self):
        frame = ttk.Frame(self._nb, style="Panel.TFrame")
        self._nb.add(frame, text="  📚  Library  ")

        # Toolbar
        tb = ttk.Frame(frame, style="Panel.TFrame")
        tb.pack(fill="x", padx=8, pady=6)
        ttk.Button(tb, text="+ Add Files",   command=self._add_files).pack(side="left", padx=(0,4))
        ttk.Button(tb, text="+ Add Folder",  command=self._add_folder).pack(side="left", padx=(0,4))
        ttk.Button(tb, text="🗑 Remove",      command=self._remove_selected,
                   style="Ghost.TButton").pack(side="left", padx=(0,4))
        ttk.Button(tb, text="↺ Reindex All", command=self._reindex_all,
                   style="Ghost.TButton").pack(side="left")

        # Progress bar (hidden until indexing)
        self._lib_progress_frame = ttk.Frame(frame, style="Panel.TFrame")
        self._lib_progress_frame.pack(fill="x", padx=8, pady=(0,4))
        self._lib_progress_label = ttk.Label(self._lib_progress_frame, text="",
                                              style="Muted.TLabel")
        self._lib_progress_label.pack(side="left")
        self._lib_progress = ttk.Progressbar(self._lib_progress_frame, mode="indeterminate",
                                              length=200)

        # Tree
        cols = ("title","pages","type","indexed")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        for col, label, width in [
            ("title","Title",400),("pages","Pages",60),("type","Type",60),("indexed","Indexed",160)
        ]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width)
        sb = ttk.Scrollbar(frame, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(8,0), pady=(0,8))
        sb.pack(side="right", fill="y", pady=(0,8), padx=(0,4))
        self._tree.bind("<Double-1>", self._open_file_from_tree)

        # Right-click menu
        self._ctx = tk.Menu(self, tearoff=0)
        self._ctx.add_command(label="Open file",    command=self._open_selected)
        self._ctx.add_command(label="Remove from library", command=self._remove_selected)
        self._tree.bind("<Button-3>", lambda e: self._ctx.post(e.x_root, e.y_root))

    # ── Search tab ──────────────────────────────────────────────────────────

    def _build_search_tab(self):
        frame = ttk.Frame(self._nb, style="Panel.TFrame")
        self._nb.add(frame, text="  🔍  Search  ")

        # ── Top search bar ──────────────────────────────────────────────
        top = ttk.Frame(frame, style="Panel.TFrame")
        top.pack(fill="x", padx=8, pady=6)

        self._search_var = tk.StringVar()
        self._search_combo = ttk.Combobox(top, textvariable=self._search_var,
                                           font=("Segoe UI", 12), width=52)
        self._search_combo.pack(side="left", fill="x", expand=True, padx=(0,6))
        self._search_combo.bind("<Return>", lambda e: self._do_search())

        ttk.Button(top, text="Search", command=self._do_search).pack(side="left", padx=(0,4))
        ttk.Button(top, text="✕", command=self._clear_search, width=2,
                   style="Ghost.TButton").pack(side="left")

        # ── Intent + expansion bar ──────────────────────────────────────
        self._intent_frame = ttk.Frame(frame, style="Panel.TFrame")
        self._intent_frame.pack(fill="x", padx=8, pady=(0,4))
        self._intent_label = ttk.Label(self._intent_frame, text="",
                                        style="Muted.TLabel", font=("Segoe UI", 9, "italic"))
        self._intent_label.pack(side="left")
        self._debug_btn = ttk.Button(self._intent_frame, text="show expansion ▸",
                                      style="Ghost.TButton", command=self._toggle_debug)
        self._debug_btn.pack(side="right")
        self._debug_expanded = False
        self._debug_frame = ttk.Frame(frame, style="Panel.TFrame")

        # ── Main area: sidebar + results ────────────────────────────────
        main = ttk.Frame(frame, style="Panel.TFrame")
        main.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Sidebar — facets
        self._sidebar = ttk.Frame(main, style="Sidebar.TFrame", width=180)
        self._sidebar.pack(side="left", fill="y", padx=(0,6))
        self._sidebar.pack_propagate(False)
        ttk.Label(self._sidebar, text="Filter results", style="Sidebar.TLabel",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(8,4))
        self._facet_vars: Dict[str, tk.StringVar] = {}
        for facet in ("author","year","file_type","tag"):
            ttk.Label(self._sidebar, text=facet.replace("_"," ").title(),
                      style="Sidebar.TLabel", font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=(6,0))
            var = tk.StringVar()
            combo = ttk.Combobox(self._sidebar, textvariable=var, state="readonly", width=18)
            combo.pack(anchor="w", padx=8, pady=(0,2))
            combo.bind("<<ComboboxSelected>>", lambda e: self._do_search())
            self._facet_vars[facet] = var
            setattr(self, f"_facet_{facet}", combo)
        ttk.Button(self._sidebar, text="Clear filters", style="Ghost.TButton",
                   command=self._clear_filters).pack(anchor="w", padx=8, pady=6)

        # Results panel
        results_outer = ttk.Frame(main, style="Panel.TFrame")
        results_outer.pack(side="left", fill="both", expand=True)

        self._results_info = ttk.Label(results_outer, text="Type a query to search your library.",
                                        style="Muted.TLabel", font=("Segoe UI", 10, "italic"))
        self._results_info.pack(anchor="w", pady=(0,4))

        canvas = tk.Canvas(results_outer, borderwidth=0, highlightthickness=0)
        sb2 = ttk.Scrollbar(results_outer, command=canvas.yview)
        canvas.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._results_inner = ttk.Frame(canvas, style="Panel.TFrame")
        self._results_window = canvas.create_window((0,0), window=self._results_inner, anchor="nw")
        self._results_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(self._results_window, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self._results_canvas = canvas

    def _toggle_debug(self):
        self._debug_expanded = not self._debug_expanded
        if self._debug_expanded:
            self._debug_frame.pack(fill="x", padx=8, pady=(0,4))
            self._debug_btn.config(text="hide expansion ▾")
        else:
            self._debug_frame.pack_forget()
            self._debug_btn.config(text="show expansion ▸")

    def _update_debug(self, debug: Dict):
        for w in self._debug_frame.winfo_children():
            w.destroy()
        t = styles.current()
        for label, terms in debug.items():
            if terms:
                row = ttk.Frame(self._debug_frame, style="Panel.TFrame")
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=f"{label}:", style="Panel.TLabel",
                          font=("Segoe UI", 8, "bold"), width=14).pack(side="left")
                ttk.Label(row, text=", ".join(str(x) for x in terms[:12]),
                          style="Panel.TLabel",
                          font=("Segoe UI", 8), foreground=t["text_muted"]).pack(side="left")

    # ── Tools tab ───────────────────────────────────────────────────────────

    def _build_tools_tab(self):
        frame = ttk.Frame(self._nb, style="Panel.TFrame")
        self._nb.add(frame, text="  🔧  Tools  ")

        # OCR section
        ttk.Label(frame, text="OCR — Make Scanned PDFs Searchable",
                  font=("Segoe UI", 11, "bold"), style="Panel.TLabel").pack(anchor="w", padx=12, pady=(12,4))
        self._tess_status = ttk.Label(frame, text=self._get_tesseract_status(),
                                       style="Muted.TLabel")
        self._tess_status.pack(anchor="w", padx=12)
        ocr_row = ttk.Frame(frame, style="Panel.TFrame")
        ocr_row.pack(anchor="w", padx=12, pady=6)
        ttk.Button(ocr_row, text="Select PDF for OCR…", command=self._run_ocr).pack(side="left", padx=(0,8))

        ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=12, pady=10)

        # Semantic embedding section
        ttk.Label(frame, text="Semantic Mode — bge-micro-v2 Embedding Model",
                  font=("Segoe UI", 11, "bold"), style="Panel.TLabel").pack(anchor="w", padx=12, pady=(0,4))
        self._embed_status_label = ttk.Label(frame, text="", style="Muted.TLabel")
        self._embed_status_label.pack(anchor="w", padx=12)
        self._update_embed_tool_status()
        ttk.Button(frame, text="View setup instructions…",
                   command=self._show_embed_help).pack(anchor="w", padx=12, pady=4)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=12, pady=10)

        # Synonym editor hint
        ttk.Label(frame, text="Synonym / Thesaurus Network",
                  font=("Segoe UI", 11, "bold"), style="Panel.TLabel").pack(anchor="w", padx=12, pady=(0,4))
        ttk.Label(frame, text=f"Edit  data/synonyms.json  to customize the expansion network.\n"
                               "Changes are picked up automatically on the next search.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", padx=12)
        ttk.Button(frame, text="Open synonyms.json…",
                   command=self._open_synonyms).pack(anchor="w", padx=12, pady=4)

    # ── Status bar ──────────────────────────────────────────────────────────

    def _build_status_bar(self):
        t = styles.current()
        sb = tk.Frame(self, bg=t["sidebar_bg"], height=24)
        sb.pack(fill="x", side="bottom")
        self._status_var = tk.StringVar(value="Ready")
        self._status_lbl = tk.Label(sb, textvariable=self._status_var, anchor="w",
                                     bg=t["sidebar_bg"], fg=t["text_muted"],
                                     font=("Segoe UI", 9), padx=8)
        self._status_lbl.pack(side="left")
        self._sem_label = tk.Label(sb, text="", anchor="e",
                                    bg=t["sidebar_bg"], fg=t["sem_off"],
                                    font=("Segoe UI", 9, "bold"), padx=8)
        self._sem_label.pack(side="right")

    def _update_semantic_status(self):
        t = styles.current()
        if self._embed_available():
            txt  = "⬤  Semantic mode: ON"
            color = t["sem_on"]
        else:
            txt  = "⬤  Semantic mode: OFF"
            color = t["sem_off"]
        self._sem_label.config(text=txt, fg=color)

    def _update_embed_tool_status(self):
        if self._embed_available():
            msg = "✅  Model loaded and ready."
        else:
            msg = "⚠️  Model not found. Click 'View setup instructions' to enable."
        self._embed_status_label.config(text=msg)

    # ── Search logic ─────────────────────────────────────────────────────────

    def _do_search(self, event=None):
        if self._conn is None:
            self._status_var.set("Still loading — please wait a moment…")
            return
        query = self._search_var.get().strip()
        if not query:
            return
        self._results_info.config(text="Searching…")
        self._clear_results()
        filters = {k: v.get() for k, v in self._facet_vars.items() if v.get()}
        self._run_in_thread(self._search_worker, query, filters)
        # Update history dropdown (safe: conn already exists)
        try:
            hist = self._get_searcher().history(self._conn)
            self._search_combo["values"] = hist
        except Exception:
            pass

    def _search_worker(self, query: str, filters: dict):
        try:
            resp = self._get_searcher().search(self._conn, query, filters=filters or None)
            self._queue.put(("search_done", resp))
        except Exception as e:
            self._queue.put(("error", f"Search failed: {e}"))

    def _handle_search_done(self, resp):
        n = len(resp.results)
        t = resp.elapsed_ms
        intents = ", ".join(resp.intents)
        self._results_info.config(
            text=f"{n} result{'s' if n != 1 else ''}  ·  {t:.0f} ms  ·  intent: {intents}"
        )
        self._intent_label.config(text=f"Detected: {intents}")
        self._update_debug(resp.expansion_debug)

        # Update facet dropdowns
        for facet, values in resp.facets.items():
            combo = getattr(self, f"_facet_{facet}", None)
            if combo:
                items = [""] + [f"{v}  ({n})" for v, n in values]
                combo["values"] = items

        self._render_results(resp.results)

    def _render_results(self, results):
        self._clear_results()
        t = styles.current()
        for i, r in enumerate(results):
            self._render_card(r, i, t)

    def _render_card(self, r, idx: int, t: dict):
        card = tk.Frame(self._results_inner, bg=t["result_bg"],
                        highlightthickness=1, highlightbackground=t["border"],
                        padx=10, pady=8)
        card.pack(fill="x", pady=(0, 6), padx=2)

        # Header row: title + score
        hdr = tk.Frame(card, bg=t["result_bg"])
        hdr.pack(fill="x")
        title_txt = f"{r.title}"
        if r.section:
            title_txt += f"  ›  {r.section}"
        tk.Label(hdr, text=title_txt, bg=t["result_bg"], fg=t["text"],
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left")
        tk.Label(hdr, text=f"{r.score:.2f}", bg=t["result_bg"], fg=t["score_fg"],
                 font=("Segoe UI", 9, "bold")).pack(side="right")

        # Meta row: page, type, structure, intents
        meta_parts = [f"p. {r.page_num}", r.file_type.upper(), r.structure_type]
        meta_parts += r.intent_labels[:2]
        meta = "  ·  ".join(meta_parts)
        tk.Label(card, text=meta, bg=t["result_bg"], fg=t["text_muted"],
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(1, 4))

        # Snippet
        snip_frame = tk.Frame(card, bg=t["snippet_bg"], padx=6, pady=4)
        snip_frame.pack(fill="x")
        tk.Label(snip_frame, text=r.snippet, bg=t["snippet_bg"], fg=t["text"],
                 font=("Segoe UI", 10), justify="left", wraplength=640,
                 anchor="w").pack(fill="x")

        # Action buttons
        btn_row = tk.Frame(card, bg=t["result_bg"])
        btn_row.pack(fill="x", pady=(6,0))
        tk.Button(btn_row, text="Open file", font=("Segoe UI", 8),
                  bg=t["tag_bg"], fg=t["tag_fg"], relief="flat", cursor="hand2",
                  command=lambda fp=r.file_path: self._open_path(fp)).pack(side="left", padx=(0,4))
        citation = f"{r.title}, p. {r.page_num}"
        if r.section:
            citation += f", {r.section}"
        tk.Button(btn_row, text="Copy citation", font=("Segoe UI", 8),
                  bg=t["tag_bg"], fg=t["tag_fg"], relief="flat", cursor="hand2",
                  command=lambda c=citation: self._copy_to_clipboard(c)).pack(side="left")

        # Hover effect
        def on_enter(e, f=card, bg=t["result_hover"]):
            f.config(bg=bg)
        def on_leave(e, f=card, bg=t["result_bg"]):
            f.config(bg=bg)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

    def _clear_results(self):
        for w in self._results_inner.winfo_children():
            w.destroy()

    def _focus_search(self):
        self._nb.select(1)
        self._search_combo.focus_set()

    def _clear_search(self):
        self._search_var.set("")
        self._clear_results()
        self._results_info.config(text="Type a query to search your library.")
        self._intent_label.config(text="")

    def _clear_filters(self):
        for var in self._facet_vars.values():
            var.set("")

    # ── Library actions ─────────────────────────────────────────────────────

    def _add_files(self):
        paths = dialogs.ask_open_files(self)
        if paths:
            self._index_paths(list(paths))

    def _add_folder(self):
        folder = dialogs.ask_open_folder(self)
        if folder:
            paths = []
            for root_dir, _, files in os.walk(folder):
                for f in files:
                    if Path(f).suffix.lower() in SUPPORTED_EXTS:
                        paths.append(os.path.join(root_dir, f))
            if paths:
                self._index_paths(paths)
            else:
                dialogs.show_info("No files", "No PDF or EPUB files found in that folder.")

    def _index_paths(self, paths: List[str]):
        self._lib_progress.pack(side="left", padx=6)
        self._lib_progress.start(10)
        self._status_var.set(f"Indexing {len(paths)} file(s)…")
        self._run_in_thread(self._index_worker, paths)

    def _index_worker(self, paths: List[str]):
        def cb(path, cur, total):
            name = Path(path).name
            self._queue.put(("status", f"Indexing {cur}/{total}: {name}"))
        try:
            counts = self._get_indexer().index_paths(paths, self._get_conn(), progress_cb=cb)
            self._queue.put(("index_done", counts))
        except Exception as e:
            self._queue.put(("error", f"Indexing error: {e}"))

    def _remove_selected(self):
        if self._conn is None:
            return
        selected = self._tree.selection()
        for iid in selected:
            fp = self._tree.item(iid, "values")[0]
            # Stored path in hidden tag
            tags = self._tree.item(iid, "tags")
            if tags:
                fp = tags[0]
            self._get_indexer().remove_file(fp, self._conn)
        self._refresh_library()

    def _reindex_all(self):
        if self._conn is None:
            return
        rows = self._conn.execute("SELECT file_path FROM documents").fetchall()
        paths = [r[0] for r in rows]
        if paths:
            self._index_paths(paths)

    def _refresh_library(self):
        if self._conn is None:
            return
        self._tree.delete(*self._tree.get_children())
        rows = self._conn.execute(
            "SELECT title, page_count, file_type, indexed_at, file_path FROM documents ORDER BY title"
        ).fetchall()
        import datetime
        for r in rows:
            indexed = datetime.datetime.fromtimestamp(r[3]).strftime("%Y-%m-%d %H:%M") if r[3] else ""
            iid = self._tree.insert("", "end",
                                     values=(r[0], r[1], r[2].upper(), indexed),
                                     tags=(r[4],))
        self._status_var.set(f"{len(rows)} document(s) in library.")

    def _open_file_from_tree(self, event):
        selected = self._tree.selection()
        if selected:
            tags = self._tree.item(selected[0], "tags")
            if tags:
                self._open_path(tags[0])

    def _open_selected(self):
        selected = self._tree.selection()
        if selected:
            tags = self._tree.item(selected[0], "tags")
            if tags:
                self._open_path(tags[0])

    # ── Tools actions ────────────────────────────────────────────────────────

    def _get_tesseract_status(self) -> str:
        try:
            import pytesseract  # type: ignore
            pytesseract.get_tesseract_version()
            return "✅  Tesseract found — OCR available."
        except Exception:
            return "⚠️  Tesseract not found. Install from https://github.com/UB-Mannheim/tesseract/wiki"

    def _run_ocr(self):
        paths = dialogs.ask_open_files(self)
        if paths:
            self._lib_progress.pack(side="left", padx=6)
            self._lib_progress.start(10)
            self._status_var.set("Running OCR…")
            self._run_in_thread(self._ocr_worker, list(paths))

    def _ocr_worker(self, paths):
        try:
            counts = self._get_indexer().index_paths(paths, self._get_conn(), ocr=True)
            self._queue.put(("index_done", counts))
        except Exception as e:
            self._queue.put(("error", f"OCR failed: {e}"))

    def _show_embed_help(self):
        from ..search.embeddings import download_instructions
        dialogs.show_text_popup(self, "Semantic Mode Setup", download_instructions())

    def _open_synonyms(self):
        from ..utils.constants import SYNONYMS_PATH
        self._open_path(str(SYNONYMS_PATH))

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _open_path(self, path: str):
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            dialogs.show_error("Could not open", str(e))

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status_var.set("Citation copied to clipboard.")

    def _toggle_theme(self):
        styles.toggle()
        styles.apply(self, self._style)

    def _show_about(self):
        dialogs.show_info(
            f"About {APP_NAME}",
            f"{APP_NAME}  v{APP_VERSION}\n\n"
            "Holistic offline PDF search engine.\n"
            "No internet. No AI API. No cloud.\n\n"
            "Five concentric circles of meaning:\n"
            "  Literal → Stem → Synonym → Concept → Embedding\n\n"
            "Ctrl+F  Search    Ctrl+O  Add files    Esc  Clear"
        )

    def _run_in_thread(self, fn, *args):
        if self._worker and self._worker.is_alive():
            return  # debounce: ignore if already running
        self._worker = threading.Thread(target=fn, args=args, daemon=True)
        self._worker.start()

    # ── Queue polling ────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg, payload = self._queue.get_nowait()
                if msg == "init_done":
                    # Background init finished — conn is already stored on self._conn
                    self._refresh_library()
                    self._update_semantic_status()
                elif msg == "search_done":
                    self._handle_search_done(payload)
                elif msg == "index_done":
                    self._lib_progress.stop()
                    self._lib_progress.pack_forget()
                    ok = payload.get("ok", 0)
                    sk = payload.get("skipped", 0)
                    fa = payload.get("failed", 0)
                    self._status_var.set(
                        f"Done — {ok} indexed, {sk} unchanged, {fa} failed."
                    )
                    self._refresh_library()
                elif msg == "status":
                    self._status_var.set(payload)
                elif msg == "error":
                    self._lib_progress.stop()
                    self._lib_progress.pack_forget()
                    dialogs.show_error("Error", payload)
                    self._status_var.set("Error — see dialog.")
        except queue.Empty:
            pass
        finally:
            self.after(_POLL_MS, self._poll_queue)
