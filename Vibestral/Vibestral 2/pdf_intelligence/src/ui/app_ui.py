# src/ui/app_ui.py
"""Tkinter UI: Library / Search / Tools tabs.
Changes: scope selector (All / selected docs), right-click 'Search this doc',
side-by-side PDF text viewer pane, pre-populated scope list.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Optional

from . import dialogs, styles
from ..index import indexer
from ..index.schema import open_db
from ..search import searcher
from ..core import pdf_parser, epub_parser
from ..utils.constants import APP_NAME, DB_PATH, DATA_DIR, SUPPORTED_EXTS, WINDOW_WIDTH, WINDOW_HEIGHT


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._mode = "light"
        self._pal = styles.apply(root, self._mode)
        self.root.title(APP_NAME)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(960, 620)

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = open_db(DB_PATH)

        self._queue: queue.Queue = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        # doc_id -> file_path for scoped search
        self._scope_doc_ids: list[int] = []   # empty = all docs

        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()
        self._refresh_library()
        self.root.after(80, self._drain_queue)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Add Files\u2026\tCtrl+O", command=self._pick_files)
        file_menu.add_command(label="Add Folder\u2026", command=self._pick_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Toggle Dark Mode\tCtrl+D", command=self._toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=lambda: dialogs.AboutDialog(self.root))
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        hdr = ttk.Frame(self.root)
        hdr.pack(fill="x")
        ttk.Label(hdr, text=f"  {APP_NAME}", font=("Segoe UI", 13, "bold")).pack(side="left", pady=8)
        ttk.Button(hdr, text="\u2600 / \u263e", command=self._toggle_theme,
                   style="Secondary.TButton").pack(side="right", padx=8, pady=4)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._tab_library = ttk.Frame(self.nb)
        self._tab_search  = ttk.Frame(self.nb)
        self._tab_tools   = ttk.Frame(self.nb)
        self.nb.add(self._tab_library, text="  Library  ")
        self.nb.add(self._tab_search,  text="  Search  ")
        self.nb.add(self._tab_tools,   text="  Tools  ")

        self._build_library_tab()
        self._build_search_tab()
        self._build_tools_tab()

    # ------------------------------------------------------------------
    # Library tab
    # ------------------------------------------------------------------
    def _build_library_tab(self) -> None:
        top = ttk.Frame(self._tab_library)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Button(top, text="+ Add Files",  command=self._pick_files).pack(side="left", padx=(0,6))
        ttk.Button(top, text="+ Add Folder", command=self._pick_folder,
                   style="Secondary.TButton").pack(side="left", padx=(0,6))
        ttk.Button(top, text="Re-scan",      command=self._rescan,
                   style="Secondary.TButton").pack(side="left")
        self.lib_status = ttk.Label(top, text="", style="Muted.TLabel")
        self.lib_status.pack(side="right", padx=8)

        self.progress = ttk.Progressbar(self._tab_library, mode="determinate")
        self.progress_label = ttk.Label(self._tab_library, text="", style="Muted.TLabel")

        list_frame = ttk.Frame(self._tab_library)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0,8))

        cols = ("title", "type", "pages", "tokens", "path")
        self.lib_tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                     selectmode="extended")
        for cid, label, w in (
            ("title","Title",320),("type","Type",60),
            ("pages","Pages",70),("tokens","Tokens",90),("path","Path",480),
        ):
            self.lib_tree.heading(cid, text=label)
            self.lib_tree.column(cid, width=w, anchor="w")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.lib_tree.yview)
        self.lib_tree.configure(yscrollcommand=vsb.set)
        self.lib_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._lib_menu = tk.Menu(self.root, tearoff=False)
        self._lib_menu.add_command(label="Open file",           command=self._open_selected)
        self._lib_menu.add_command(label="Search this document",command=self._search_selected_doc)
        self._lib_menu.add_command(label="Search selected docs",command=self._search_selected_docs)
        self._lib_menu.add_separator()
        self._lib_menu.add_command(label="Remove from library", command=self._remove_selected)
        self.lib_tree.bind("<Button-3>", self._show_lib_menu)
        self.lib_tree.bind("<Double-1>", lambda _e: self._open_selected())

    def _refresh_library(self) -> None:
        for iid in self.lib_tree.get_children():
            self.lib_tree.delete(iid)
        docs = indexer.list_documents(self.conn)
        for d in docs:
            self.lib_tree.insert("", "end", iid=str(d["id"]),
                values=(d["title"], d["file_type"].upper(),
                        d["page_count"], d["total_tokens"], d["file_path"]))
        n_chunks, _ = indexer.corpus_stats(self.conn)
        self.lib_status.configure(text=f"{len(docs)} doc(s) \u00b7 {n_chunks} chunks")
        self._refresh_scope_list()

    def _show_lib_menu(self, event: tk.Event) -> None:
        row = self.lib_tree.identify_row(event.y)
        if row:
            if row not in self.lib_tree.selection():
                self.lib_tree.selection_set(row)
            self._lib_menu.post(event.x_root, event.y_root)

    def _open_selected(self) -> None:
        sel = self.lib_tree.selection()
        if sel:
            self._open_file(str(self.lib_tree.item(sel[0])["values"][4]))

    def _remove_selected(self) -> None:
        sel = self.lib_tree.selection()
        if not sel:
            return
        if not dialogs.ask_yes_no("Remove",
                f"Remove {len(sel)} document(s) from the index?\nOriginal files are NOT deleted."):
            return
        for iid in sel:
            try:
                indexer.remove_document(self.conn, int(iid))
            except Exception as e:
                dialogs.show_error("Remove failed", str(e))
        self._refresh_library()

    def _search_selected_doc(self) -> None:
        """Switch to Search tab scoped to the single right-clicked document."""
        sel = self.lib_tree.selection()
        if not sel:
            return
        self._scope_doc_ids = [int(sel[0])]
        title = self.lib_tree.item(sel[0])["values"][0]
        self._update_scope_label(f"Scope: {title}")
        self.nb.select(1)
        self._search_entry.focus_set()

    def _search_selected_docs(self) -> None:
        """Scope search to all currently selected library rows."""
        sel = self.lib_tree.selection()
        if not sel:
            return
        self._scope_doc_ids = [int(iid) for iid in sel]
        self._update_scope_label(f"Scope: {len(sel)} selected doc(s)")
        self.nb.select(1)
        self._search_entry.focus_set()


    # ------------------------------------------------------------------
    # Search tab
    # ------------------------------------------------------------------
    def _build_search_tab(self) -> None:
        # --- top bar ---
        top = ttk.Frame(self._tab_search)
        top.pack(fill="x", padx=10, pady=8)
        self.search_var = tk.StringVar()
        self._search_entry = ttk.Entry(top, textvariable=self.search_var, font=("Segoe UI", 12))
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._search_entry.bind("<Return>", lambda _e: self._do_search())
        ttk.Button(top, text="Search", style="Accent.TButton",
                   command=self._do_search).pack(side="left", padx=(8,0))
        ttk.Button(top, text="\u2715", command=self._clear_search,
                   style="Secondary.TButton").pack(side="left", padx=(4,0))

        # --- scope + history row ---
        meta = ttk.Frame(self._tab_search)
        meta.pack(fill="x", padx=10, pady=(0,4))

        # Scope selector
        ttk.Label(meta, text="Scope:", style="Muted.TLabel").pack(side="left")
        self._scope_var = tk.StringVar(value="All documents")
        self._scope_combo = ttk.Combobox(meta, textvariable=self._scope_var,
                                         state="readonly", width=35)
        self._scope_combo.pack(side="left", padx=(4,12))
        self._scope_combo.bind("<<ComboboxSelected>>", self._on_scope_change)
        ttk.Button(meta, text="Clear scope", command=self._clear_scope,
                   style="Secondary.TButton").pack(side="left", padx=(0,12))

        ttk.Label(meta, text="Recent:", style="Muted.TLabel").pack(side="left")
        self._hist_var = tk.StringVar()
        self._hist_combo = ttk.Combobox(meta, textvariable=self._hist_var,
                                        state="readonly", width=30)
        self._hist_combo.pack(side="left", padx=(4,0))
        self._hist_combo.bind("<<ComboboxSelected>>", self._use_history)

        self.search_status = ttk.Label(meta, text="", style="Muted.TLabel")
        self.search_status.pack(side="right", padx=8)

        # --- scope label (set by right-click) ---
        self._scope_lbl_var = tk.StringVar(value="")
        self._scope_lbl = ttk.Label(self._tab_search, textvariable=self._scope_lbl_var,
                                    style="Muted.TLabel")
        self._scope_lbl.pack(anchor="w", padx=10)

        # --- main pane: sidebar | results | viewer ---
        pane = ttk.Frame(self._tab_search)
        pane.pack(fill="both", expand=True, padx=10, pady=(0,8))

        # Facet sidebar
        sidebar = ttk.LabelFrame(pane, text="Filters", width=160)
        sidebar.pack(side="left", fill="y", padx=(0,6))
        sidebar.pack_propagate(False)
        self._sidebar = sidebar
        self._facet_vars: dict[str, tk.StringVar] = {}
        self._build_facet_sidebar()

        # Results list (left half of remaining space)
        results_frame = ttk.Frame(pane)
        results_frame.pack(side="left", fill="both", expand=True)

        self.results_canvas = tk.Canvas(results_frame, highlightthickness=0,
                                        bg=self._pal["bg"])
        vsb = ttk.Scrollbar(results_frame, orient="vertical",
                             command=self.results_canvas.yview)
        self.results_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.results_canvas.pack(side="left", fill="both", expand=True)
        self.results_inner = ttk.Frame(self.results_canvas)
        self._rwin = self.results_canvas.create_window(
            (0,0), window=self.results_inner, anchor="nw")
        self.results_inner.bind(
            "<Configure>",
            lambda _e: self.results_canvas.configure(
                scrollregion=self.results_canvas.bbox("all")))
        self.results_canvas.bind(
            "<Configure>",
            lambda e: self.results_canvas.itemconfigure(self._rwin, width=e.width))
        self.results_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.results_canvas.yview_scroll(int(-e.delta/120), "units"))

        # PDF viewer pane (right side, collapsible)
        self._viewer_visible = False
        self._viewer_frame = ttk.LabelFrame(pane, text="Document Viewer", width=420)
        # built lazily when first result is clicked
        self._viewer_page_cache: dict[tuple[str, int], str] = {}  # (file_path, page_num) -> text

        self._refresh_history()
        self._refresh_scope_list()

    def _build_facet_sidebar(self) -> None:
        for w in self._sidebar.winfo_children():
            w.destroy()
        self._facet_vars.clear()
        for label, key in (("Author","author"),("Year","year")):
            ttk.Label(self._sidebar, text=label).pack(anchor="w", padx=8, pady=(8,2))
            v = tk.StringVar()
            ttk.Entry(self._sidebar, textvariable=v, width=18).pack(padx=8, fill="x")
            self._facet_vars[key] = v
        ttk.Label(self._sidebar, text="File Type").pack(anchor="w", padx=8, pady=(8,2))
        ft_var = tk.StringVar()
        ttk.Combobox(self._sidebar, textvariable=ft_var,
                     values=["","pdf","epub"], state="readonly",
                     width=16).pack(padx=8, fill="x")
        self._facet_vars["file_type"] = ft_var
        ttk.Button(self._sidebar, text="Apply",
                   command=self._do_search).pack(padx=8, pady=8, fill="x")
        ttk.Button(self._sidebar, text="Clear",
                   command=self._clear_filters,
                   style="Secondary.TButton").pack(padx=8, fill="x")

    def _refresh_scope_list(self) -> None:
        docs = indexer.list_documents(self.conn)
        values = ["All documents"] + [d["title"] for d in docs]
        self._scope_combo["values"] = values
        self._scope_combo.set("All documents")
        # store id mapping by position
        self._scope_docs = docs  # list of dicts in same order

    def _on_scope_change(self, _e=None) -> None:
        val = self._scope_var.get()
        if val == "All documents":
            self._scope_doc_ids = []
            self._update_scope_label("")
        else:
            for d in self._scope_docs:
                if d["title"] == val:
                    self._scope_doc_ids = [d["id"]]
                    self._update_scope_label(f"Scope: {val}")
                    break

    def _update_scope_label(self, text: str) -> None:
        self._scope_lbl_var.set(text)

    def _clear_scope(self) -> None:
        self._scope_doc_ids = []
        self._scope_var.set("All documents")
        self._update_scope_label("")

    def _apply_filters(self) -> None:
        self._do_search()

    def _clear_filters(self) -> None:
        for v in self._facet_vars.values():
            v.set("")
        self._do_search()

    def _do_search(self) -> None:
        q = self.search_var.get().strip()
        if not q:
            return
        filters = {k: v.get().strip() for k, v in self._facet_vars.items() if v.get().strip()}
        scope_ids = list(self._scope_doc_ids)

        def work():
            try:
                resp = searcher.search(self.conn, q, filters=filters or None, doc_ids=scope_ids or None)
                self._queue.put(("search_done", resp))
            except Exception as e:
                self._queue.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()
        self.search_status.configure(text="Searching\u2026")

    def _clear_search(self) -> None:
        self.search_var.set("")
        for w in self.results_inner.winfo_children():
            w.destroy()
        self.search_status.configure(text="")
        self._hide_viewer()

    def _render_results(self, resp: searcher.SearchResponse) -> None:
        for w in self.results_inner.winfo_children():
            w.destroy()
        fb = " [fuzzy]" if resp.used_fallback else ""
        scope_note = f" (scoped)" if self._scope_doc_ids else ""
        self.search_status.configure(
            text=f"{len(resp.results)} result(s) \u00b7 {resp.elapsed_ms:.1f} ms{fb}{scope_note}")
        if not resp.results:
            ttk.Label(self.results_inner,
                      text="No matches. Try fewer or different keywords.",
                      style="Muted.TLabel").pack(anchor="w", padx=8, pady=12)
            return
        pal = self._pal
        for r in resp.results:
            card = tk.Frame(self.results_inner, bg=pal["card_bg"], bd=0,
                            highlightbackground=pal["border"], highlightthickness=1)
            card.pack(fill="x", pady=3, padx=2)
            tk.Frame(card, bg=pal["result_left"], width=4).pack(side="left", fill="y")
            body = tk.Frame(card, bg=pal["card_bg"], padx=10, pady=6)
            body.pack(side="left", fill="both", expand=True)

            title_row = tk.Frame(body, bg=pal["card_bg"])
            title_row.pack(fill="x")
            tk.Label(title_row, text=r.title, font=("Segoe UI", 10, "bold"),
                     bg=pal["card_bg"], fg=pal["fg"], anchor="w").pack(side="left")
            tk.Label(title_row, text=f"{r.score*100:.0f}%",
                     font=("Segoe UI", 9), bg=pal["card_bg"],
                     fg=pal["score_fg"]).pack(side="right")

            meta_parts = []
            if r.section:
                meta_parts.append(f"\u00a7 {r.section}")
            meta_parts.append(f"p. {r.page_num}")
            if r.author:
                meta_parts.append(r.author)
            if r.year:
                meta_parts.append(str(r.year))
            if r.file_type:
                meta_parts.append(r.file_type.upper())
            tk.Label(body, text="  \u00b7  ".join(p for p in meta_parts if p),
                     font=("Segoe UI", 9), bg=pal["card_bg"],
                     fg=pal["muted"], anchor="w").pack(fill="x")

            tk.Label(body, text=r.snippet, font=("Segoe UI", 10),
                     bg=pal["card_bg"], fg=pal["fg"],
                     anchor="w", justify="left", wraplength=380).pack(fill="x", pady=(3,0))

            btn_row = tk.Frame(body, bg=pal["card_bg"])
            btn_row.pack(fill="x", pady=(4,0))
            _fp, _pg = r.file_path, r.page_num
            ttk.Button(btn_row, text="Open file",
                       command=lambda p=_fp: self._open_file(p),
                       style="Secondary.TButton").pack(side="left")
            ttk.Button(btn_row, text="View text",
                       command=lambda p=_fp, pg=_pg, t=r.title: self._show_viewer(p, pg, t),
                       style="Secondary.TButton").pack(side="left", padx=(4,0))
            citation = f"{r.title}, p. {r.page_num}"
            if r.author:
                citation = f"{r.author} \u2014 {citation}"
            ttk.Button(btn_row, text="Copy citation",
                       command=lambda c=citation: (
                           self.root.clipboard_clear(), self.root.clipboard_append(c)),
                       style="Secondary.TButton").pack(side="left", padx=(4,0))

    def _refresh_history(self) -> None:
        hist = searcher.history(self.conn)
        self._hist_combo["values"] = hist
        if hist:
            self._hist_combo.set(hist[0])

    def _use_history(self, _e=None) -> None:
        q = self._hist_var.get()
        if q:
            self.search_var.set(q)
            self._do_search()

    # ------------------------------------------------------------------
    # PDF viewer pane
    # ------------------------------------------------------------------
    def _show_viewer(self, file_path: str, page_num: int, title: str) -> None:
        pal = self._pal
        if not self._viewer_visible:
            self._viewer_frame.pack(side="right", fill="both", expand=False,
                                    padx=(6,0))
            self._viewer_frame.configure(width=420)
            self._viewer_visible = True

            # Build viewer widgets once
            ctrl = ttk.Frame(self._viewer_frame)
            ctrl.pack(fill="x", padx=6, pady=4)
            self._viewer_title_var = tk.StringVar()
            ttk.Label(ctrl, textvariable=self._viewer_title_var,
                      style="Muted.TLabel").pack(side="left", fill="x", expand=True)
            ttk.Button(ctrl, text="\u2715 Close", command=self._hide_viewer,
                       style="Secondary.TButton").pack(side="right")

            nav = ttk.Frame(self._viewer_frame)
            nav.pack(fill="x", padx=6)
            ttk.Button(nav, text="\u25c4 Prev", command=self._viewer_prev,
                       style="Secondary.TButton").pack(side="left")
            self._viewer_page_var = tk.StringVar()
            ttk.Label(nav, textvariable=self._viewer_page_var,
                      style="Muted.TLabel").pack(side="left", padx=8)
            ttk.Button(nav, text="Next \u25ba", command=self._viewer_next,
                       style="Secondary.TButton").pack(side="left")

            self._viewer_text = tk.Text(
                self._viewer_frame, wrap="word", font=("Segoe UI", 10),
                bg=pal["card_bg"], fg=pal["fg"],
                relief="flat", state="disabled", padx=8, pady=8)
            vsb2 = ttk.Scrollbar(self._viewer_frame, orient="vertical",
                                  command=self._viewer_text.yview)
            self._viewer_text.configure(yscrollcommand=vsb2.set)
            vsb2.pack(side="right", fill="y")
            self._viewer_text.pack(fill="both", expand=True, padx=4, pady=4)

        self._viewer_file = file_path
        self._viewer_page = page_num
        self._viewer_title_var.set(title[:50])
        self._load_viewer_page()

    def _load_viewer_page(self) -> None:
        cache_key = (self._viewer_file, self._viewer_page)
        if cache_key in self._viewer_page_cache:
            # Cache hit - instant load
            text = self._viewer_page_cache[cache_key]
            try:
                pages = list(pdf_parser.extract_pages(Path(self._viewer_file)))
                total = len(pages)
                self._set_viewer_text(text, self._viewer_page, total)
            except Exception:
                self._set_viewer_text(text, self._viewer_page, 1)
            return

        def work():
            try:
                pages = list(pdf_parser.extract_pages(Path(self._viewer_file)))
                total = len(pages)
                pg = max(1, min(self._viewer_page, total))
                text = next((p.text for p in pages if p.page_num == pg), "")
                self._queue.put(("viewer_text", text, pg, total))
            except Exception as e:
                self._queue.put(("viewer_text", f"[Error: {e}]", 1, 1))
        threading.Thread(target=work, daemon=True).start()
        self._viewer_page_var.set("Loading\u2026")

    def _set_viewer_text(self, text: str, page: int, total: int) -> None:
        self._viewer_page = page
        self._viewer_page_var.set(f"p. {page} / {total}")
        self._viewer_text.configure(state="normal")
        self._viewer_text.delete("1.0", "end")
        self._viewer_text.insert("end", text or "[No text on this page]")
        self._viewer_text.configure(state="disabled")
        self._viewer_text.yview_moveto(0)
        # Cache this page (LRU: keep last 10 pages)
        cache_key = (self._viewer_file, page)
        self._viewer_page_cache[cache_key] = text
        if len(self._viewer_page_cache) > 10:
            # Evict oldest entry
            oldest = next(iter(self._viewer_page_cache))
            del self._viewer_page_cache[oldest]

    def _viewer_prev(self) -> None:
        if self._viewer_page > 1:
            self._viewer_page -= 1
            self._load_viewer_page()

    def _viewer_next(self) -> None:
        self._viewer_page += 1
        self._load_viewer_page()

    def _hide_viewer(self) -> None:
        self._viewer_frame.pack_forget()
        self._viewer_visible = False


    # ------------------------------------------------------------------
    # Tools tab
    # ------------------------------------------------------------------
    def _build_tools_tab(self) -> None:
        frame = ttk.Frame(self._tab_tools, padding=20)
        frame.pack(fill="both", expand=True)

        ocr_frame = ttk.LabelFrame(frame, text="OCR \u2014 Make Scanned PDFs Searchable")
        ocr_frame.pack(fill="x", pady=(0,16))
        tess_ok = pdf_parser.tesseract_available()
        tk.Label(ocr_frame,
                 text=("\u2714 Tesseract found \u2014 OCR ready" if tess_ok else
                       "\u2718 Tesseract not found \u2014 install from https://github.com/UB-Mannheim/tesseract/wiki"),
                 fg="#22c55e" if tess_ok else "#ef4444",
                 bg=self._pal["frame_bg"]).pack(anchor="w", padx=8, pady=4)
        ttk.Label(ocr_frame,
                  text="Select a scanned PDF and click 'Run OCR' to extract text.\n"
                       "The result is re-indexed and becomes searchable.",
                  style="Muted.TLabel").pack(anchor="w", padx=8, pady=(0,8))
        ocr_row = ttk.Frame(ocr_frame)
        ocr_row.pack(fill="x", padx=8, pady=(0,8))
        self._ocr_path_var = tk.StringVar(value="No file selected")
        ttk.Label(ocr_row, textvariable=self._ocr_path_var,
                  style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(ocr_row, text="Select PDF\u2026",
                   command=self._ocr_pick).pack(side="left", padx=(6,0))
        self._ocr_run_btn = ttk.Button(ocr_frame, text="Run OCR & Index",
                                       command=self._run_ocr,
                                       state="normal" if tess_ok else "disabled")
        self._ocr_run_btn.pack(padx=8, pady=(0,8), anchor="w")
        self._ocr_file = ""
        self._ocr_progress = ttk.Progressbar(ocr_frame, mode="determinate")
        self._ocr_status = ttk.Label(ocr_frame, text="", style="Muted.TLabel")
        self._ocr_status.pack(padx=8, pady=(0,8), anchor="w")

        epub_frame = ttk.LabelFrame(frame, text="EPUB \u2192 PDF Converter")
        epub_frame.pack(fill="x", pady=(0,16))
        rl_ok = epub_parser._HAS_REPORTLAB
        tk.Label(epub_frame,
                 text=("\u2714 reportlab found \u2014 conversion ready" if rl_ok else
                       "\u2718 reportlab not installed \u2014 run: pip install reportlab"),
                 fg="#22c55e" if rl_ok else "#ef4444",
                 bg=self._pal["frame_bg"]).pack(anchor="w", padx=8, pady=4)
        ttk.Label(epub_frame, text="Convert an EPUB file to a simple searchable PDF.",
                  style="Muted.TLabel").pack(anchor="w", padx=8, pady=(0,8))
        epub_row = ttk.Frame(epub_frame)
        epub_row.pack(fill="x", padx=8, pady=(0,8))
        self._epub_path_var = tk.StringVar(value="No file selected")
        ttk.Label(epub_row, textvariable=self._epub_path_var,
                  style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(epub_row, text="Select EPUB\u2026",
                   command=self._epub_pick).pack(side="left", padx=(6,0))
        self._epub_convert_btn = ttk.Button(epub_frame, text="Convert & Save PDF",
                                            command=self._run_epub_convert,
                                            state="normal" if rl_ok else "disabled")
        self._epub_convert_btn.pack(padx=8, pady=(0,8), anchor="w")
        self._epub_file = ""
        self._epub_status = ttk.Label(epub_frame, text="", style="Muted.TLabel")
        self._epub_status.pack(padx=8, pady=(0,8), anchor="w")

    # ------------------------------------------------------------------
    # File / indexing handlers
    # ------------------------------------------------------------------
    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select PDF / EPUB files",
            filetypes=[("Documents","*.pdf *.epub"),("PDF","*.pdf"),
                       ("EPUB","*.epub"),("All","*.*")])
        if paths:
            self._start_indexing([Path(p) for p in paths])

    def _pick_folder(self) -> None:
        d = filedialog.askdirectory(title="Add a folder to the library")
        if d:
            self._start_indexing([Path(d)])

    def _rescan(self) -> None:
        docs = indexer.list_documents(self.conn)
        paths = [Path(d["file_path"]) for d in docs if Path(d["file_path"]).exists()]
        if not paths:
            self.lib_status.configure(text="Nothing to re-scan.")
            return
        self._start_indexing(paths)

    def _start_indexing(self, paths: list[Path]) -> None:
        if self._worker and self._worker.is_alive():
            dialogs.show_info("Busy", "An indexing job is already running.")
            return
        def work():
            def cb(msg, done, total):
                pct = 0 if total <= 0 else int(done * 100 / total)
                self._queue.put(("progress", msg, pct, done, total))
            try:
                stats = indexer.index_paths(self.conn, paths, ocr=False, progress=cb)
                self._queue.put(("indexed_done", stats))
            except Exception as e:
                self._queue.put(("error", str(e)))
        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self.progress.pack(fill="x", padx=10, pady=(0,2))
        self.progress_label.pack(anchor="w", padx=10)
        self.progress.configure(value=0, maximum=100)
        self.progress_label.configure(text="Starting\u2026")

    def _ocr_pick(self) -> None:
        path = filedialog.askopenfilename(title="Select a PDF to OCR",
                                          filetypes=[("PDF","*.pdf")])
        if path:
            self._ocr_file = path
            self._ocr_path_var.set(Path(path).name)

    def _run_ocr(self) -> None:
        if not self._ocr_file:
            dialogs.show_error("No file", "Please select a PDF file first.")
            return
        self._ocr_progress.pack(fill="x", padx=8, pady=(0,4))
        self._ocr_progress.configure(value=0, maximum=100)
        self._ocr_status.configure(text="Running OCR\u2026")
        self._ocr_run_btn.configure(state="disabled")
        def work():
            def cb(msg, done, total):
                pct = 0 if total <= 0 else int(done * 100 / total)
                self._queue.put(("ocr_progress", msg, pct))
            try:
                stats = indexer.index_paths(self.conn, [Path(self._ocr_file)],
                                            ocr=True, progress=cb)
                self._queue.put(("ocr_done", stats))
            except Exception as e:
                self._queue.put(("error", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _epub_pick(self) -> None:
        path = filedialog.askopenfilename(title="Select an EPUB",
                                          filetypes=[("EPUB","*.epub")])
        if path:
            self._epub_file = path
            self._epub_path_var.set(Path(path).name)

    def _run_epub_convert(self) -> None:
        if not self._epub_file:
            dialogs.show_error("No file", "Please select an EPUB file first.")
            return
        out = filedialog.asksaveasfilename(
            title="Save PDF as", defaultextension=".pdf",
            initialfile=Path(self._epub_file).with_suffix(".pdf").name,
            filetypes=[("PDF","*.pdf")])
        if not out:
            return
        self._epub_status.configure(text="Converting\u2026")
        self._epub_convert_btn.configure(state="disabled")
        def work():
            ok, msg = epub_parser.to_pdf(Path(self._epub_file), Path(out))
            self._queue.put(("epub_done", ok, msg, out))
        threading.Thread(target=work, daemon=True).start()

    def _open_file(self, path: str) -> None:
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(Path(path).resolve().as_uri())
        except Exception as e:
            dialogs.show_error("Open failed", str(e))

    # ------------------------------------------------------------------
    # Theme / shortcuts
    # ------------------------------------------------------------------
    def _toggle_theme(self) -> None:
        self._mode = "dark" if self._mode == "light" else "light"
        self._pal = styles.apply(self.root, self._mode)
        self.results_canvas.configure(bg=self._pal["bg"])

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-l>", lambda _e: (self.nb.select(1), self._search_entry.focus_set()))
        self.root.bind("<Control-f>", lambda _e: (self.nb.select(1), self._search_entry.focus_set()))
        self.root.bind("<Control-o>", lambda _e: self._pick_files())
        self.root.bind("<Control-d>", lambda _e: self._toggle_theme())
        self.root.bind("<F5>",        lambda _e: self._rescan())
        self.root.bind("<Escape>",    lambda _e: self._clear_search())

    # ------------------------------------------------------------------
    # Queue pump
    # ------------------------------------------------------------------
    def _drain_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, label, pct, done, total = msg
                    self.progress.configure(value=pct, maximum=100)
                    self.progress_label.configure(text=f"{label}  ({done}/{total})")
                elif kind == "indexed_done":
                    _, stats = msg
                    self.progress.configure(value=100)
                    self.progress_label.configure(
                        text=(f"Done. indexed={stats['indexed']} "
                              f"skipped={stats['skipped']} failed={stats['failed']}"))
                    self._refresh_library()
                    self._refresh_history()
                elif kind == "search_done":
                    _, resp = msg
                    self._render_results(resp)
                    self._refresh_history()
                elif kind == "viewer_text":
                    _, text, page, total = msg
                    self._set_viewer_text(text, page, total)
                elif kind == "ocr_progress":
                    _, label, pct = msg
                    self._ocr_progress.configure(value=pct, maximum=100)
                    self._ocr_status.configure(text=label)
                elif kind == "ocr_done":
                    _, stats = msg
                    self._ocr_progress.pack_forget()
                    self._ocr_run_btn.configure(state="normal")
                    if stats["indexed"]:
                        self._ocr_status.configure(
                            text=f"\u2714 OCR complete \u2014 {stats['indexed']} file(s) indexed.")
                        self._refresh_library()
                    else:
                        self._ocr_status.configure(text="\u2718 OCR failed.")
                elif kind == "epub_done":
                    _, ok, msg_text, save_path = msg
                    self._epub_convert_btn.configure(state="normal")
                    if ok:
                        self._epub_status.configure(text=f"\u2714 Saved: {save_path}")
                        if dialogs.ask_yes_no("Saved", "PDF saved.\nAdd it to the library?"):
                            self._start_indexing([Path(save_path)])
                    else:
                        self._epub_status.configure(text=f"\u2718 {msg_text}")
                elif kind == "error":
                    dialogs.show_error("Error", msg[1])
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def shutdown(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def run() -> None:
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.shutdown(), root.destroy()))
    root.mainloop()
