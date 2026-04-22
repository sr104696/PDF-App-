"""
app_ui.py — Main Tkinter application (Library / Search / Tools tabs).

Architecture:
  - All long-running work runs on daemon threads.
  - Results are posted back to the UI via root.after(0, callback) which
    is thread-safe (Tkinter event-queue bridging).
  - A queue.Queue is also polled by after() for streaming progress updates.

Features implemented:
  [x] Three tabs: Library, Search, Tools
  [x] Drag-and-drop equivalent: file-chooser button + Ctrl+O
  [x] Keyboard shortcuts: Ctrl+F → focus search, Ctrl+O → add files, Esc → clear
  [x] Search history dropdown (last 10 queries)
  [x] Faceted sidebar (author, year, file type)
  [x] Progress bar during indexing / OCR
  [x] Dark / light mode toggle
  [x] Threaded search (UI never freezes)
  [x] Open-file button on each result card (os.startfile)
  [x] OCR / EPUB→PDF Tools tab
  [x] Tesseract availability indicator
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from src.ui.styles import apply_theme
from src.ui.dialogs import ProgressDialog, AboutDialog, show_error, show_info, ask_yes_no
from src.index.indexer import (
    ensure_db, index_paths, list_documents, delete_document,
    get_search_history, DB_PATH,
)
from src.search.searcher import search as do_search, SearchResponse
from src.core.pdf_parser import tesseract_available
from src.core.epub_parser import epub_to_pdf, _HAS_REPORTLAB
from src.utils.constants import (
    APP_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, DB_PATH as _DB_PATH,
    SUPPORTED_EXTENSIONS,
)


class AppUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(800, 560)

        self._dark = False
        self._pal = apply_theme(self.root, self._dark)
        self._queue: queue.Queue = queue.Queue()

        # State
        self._filters: dict[str, str] = {}
        self._last_response: SearchResponse | None = None

        # DB
        ensure_db()

        # Build UI
        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()

        # Start queue polling
        self._poll_queue()

    # ── Menu ─────────────────────────────────────────────────────────────────
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Add Files…\tCtrl+O", command=self._add_files)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Toggle Dark Mode\tCtrl+D", command=self._toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=lambda: AboutDialog(self.root))
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    # ── Top-level layout ──────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        # Header bar
        hdr = ttk.Frame(self.root)
        hdr.pack(fill="x", padx=0, pady=0)
        ttk.Label(hdr, text=f"  {APP_TITLE}", font=("", 13, "bold")).pack(side="left", pady=8)
        ttk.Button(hdr, text="☀ / ☾", command=self._toggle_theme,
                   style="Secondary.TButton").pack(side="right", padx=8, pady=4)

        # Notebook
        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._tab_library = ttk.Frame(self._notebook)
        self._tab_search = ttk.Frame(self._notebook)
        self._tab_tools = ttk.Frame(self._notebook)

        self._notebook.add(self._tab_library, text="  Library  ")
        self._notebook.add(self._tab_search, text="  Search  ")
        self._notebook.add(self._tab_tools, text="  Tools  ")

        self._build_library_tab()
        self._build_search_tab()
        self._build_tools_tab()

    # ── Library tab ───────────────────────────────────────────────────────────
    def _build_library_tab(self) -> None:
        top = ttk.Frame(self._tab_library)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Button(top, text="+ Add Files", command=self._add_files).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="+ Add Folder", command=self._add_folder,
                   style="Secondary.TButton").pack(side="left")

        self._lib_status = tk.StringVar(value="")
        ttk.Label(top, textvariable=self._lib_status, foreground=self._pal["muted"]).pack(
            side="right", padx=8
        )

        # Progress bar (hidden until indexing)
        self._lib_progress_var = tk.DoubleVar(value=0)
        self._lib_progress = ttk.Progressbar(
            self._tab_library, variable=self._lib_progress_var, maximum=100
        )

        # Library list
        list_frame = ttk.Frame(self._tab_library)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        cols = ("title", "pages", "type", "year", "indexed")
        self._lib_tree = ttk.Treeview(
            list_frame, columns=cols, show="headings", selectmode="browse"
        )
        self._lib_tree.heading("title",   text="Title")
        self._lib_tree.heading("pages",   text="Pages")
        self._lib_tree.heading("type",    text="Type")
        self._lib_tree.heading("year",    text="Year")
        self._lib_tree.heading("indexed", text="Indexed")
        self._lib_tree.column("title",   width=350, minwidth=120)
        self._lib_tree.column("pages",   width=60,  anchor="center")
        self._lib_tree.column("type",    width=60,  anchor="center")
        self._lib_tree.column("year",    width=60,  anchor="center")
        self._lib_tree.column("indexed", width=140, anchor="center")

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._lib_tree.yview)
        self._lib_tree.configure(yscrollcommand=vsb.set)
        self._lib_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Right-click context menu
        self._lib_menu = tk.Menu(self.root, tearoff=False)
        self._lib_menu.add_command(label="Open file", command=self._open_selected_file)
        self._lib_menu.add_command(label="Remove from library", command=self._remove_selected)
        self._lib_tree.bind("<Button-3>", self._show_lib_menu)
        self._lib_tree.bind("<Double-1>", lambda _e: self._open_selected_file())

        self._lib_doc_map: dict[str, dict] = {}  # iid → doc dict
        self._refresh_library()

    def _refresh_library(self) -> None:
        for item in self._lib_tree.get_children():
            self._lib_tree.delete(item)
        self._lib_doc_map.clear()

        import datetime
        docs = list_documents()
        for doc in docs:
            ts = doc.get("indexedAt") or 0
            try:
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_str = ""
            iid = self._lib_tree.insert(
                "", "end",
                values=(
                    doc.get("title", ""),
                    doc.get("pageCount", ""),
                    (doc.get("fileType") or "").upper(),
                    doc.get("year", "") or "",
                    dt_str,
                ),
            )
            self._lib_doc_map[iid] = doc

        self._lib_status.set(f"{len(docs)} document(s) in library")

    def _show_lib_menu(self, event: tk.Event) -> None:
        row = self._lib_tree.identify_row(event.y)
        if row:
            self._lib_tree.selection_set(row)
            self._lib_menu.post(event.x_root, event.y_root)

    def _open_selected_file(self) -> None:
        sel = self._lib_tree.selection()
        if not sel:
            return
        doc = self._lib_doc_map.get(sel[0])
        if doc:
            path = doc.get("filePath", "")
            if os.path.exists(path):
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    os.system(f'open "{path}"')
                else:
                    os.system(f'xdg-open "{path}"')
            else:
                show_error("Not found", f"File no longer exists:\n{path}")

    def _remove_selected(self) -> None:
        sel = self._lib_tree.selection()
        if not sel:
            return
        doc = self._lib_doc_map.get(sel[0])
        if doc and ask_yes_no("Remove", f"Remove '{doc['title']}' from the library?\nThe original file is NOT deleted."):
            delete_document(doc["id"])
            self._refresh_library()

    # ── Add files / folder ────────────────────────────────────────────────────
    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select PDF or EPUB files",
            filetypes=[
                ("Supported files", "*.pdf *.epub"),
                ("PDF files", "*.pdf"),
                ("EPUB files", "*.epub"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self._start_indexing(list(paths))

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder to index")
        if not folder:
            return
        paths = []
        for root_dir, _dirs, files in os.walk(folder):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTENSIONS:
                    paths.append(os.path.join(root_dir, fn))
        if not paths:
            show_info("No files found", "No PDF or EPUB files found in that folder.")
            return
        self._start_indexing(paths)

    def _start_indexing(self, paths: list[str]) -> None:
        self._notebook.select(0)  # switch to Library tab
        self._lib_progress.pack(fill="x", padx=10, pady=(0, 4))
        self._lib_progress_var.set(0)
        self._lib_status.set(f"Indexing {len(paths)} file(s)…")

        def _worker():
            total = len(paths)

            def _cb(fp, fi, ft, pg, pgt):
                pct = ((fi - 1) / total * 100) + (pg / max(pgt, 1) * 100 / total)
                fn = os.path.basename(fp)
                self._queue.put(("progress", f"[{fi}/{ft}] {fn}", min(pct, 99)))

            result = index_paths(paths, progress_cb=_cb)
            self._queue.put(("index_done", result))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Search tab ────────────────────────────────────────────────────────────
    def _build_search_tab(self) -> None:
        # ── Top: search bar ──
        top = ttk.Frame(self._tab_search)
        top.pack(fill="x", padx=10, pady=8)

        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(top, textvariable=self._search_var, font=("", 12))
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._search_entry.bind("<Return>", lambda _e: self._run_search())

        ttk.Button(top, text="Search", command=self._run_search).pack(side="left")
        ttk.Button(top, text="✕", command=self._clear_search,
                   style="Secondary.TButton").pack(side="left", padx=(4, 0))

        # History dropdown
        hist_frame = ttk.Frame(self._tab_search)
        hist_frame.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(hist_frame, text="Recent: ", foreground=self._pal["muted"]).pack(side="left")
        self._hist_var = tk.StringVar()
        self._hist_combo = ttk.Combobox(
            hist_frame, textvariable=self._hist_var, state="readonly", width=40
        )
        self._hist_combo.pack(side="left")
        self._hist_combo.bind("<<ComboboxSelected>>", self._use_history)
        self._refresh_history()

        # Search status
        self._search_status = tk.StringVar(value="")
        ttk.Label(hist_frame, textvariable=self._search_status,
                  foreground=self._pal["muted"]).pack(side="right", padx=8)

        # ── Main area: facet sidebar + results ──
        pane = ttk.Frame(self._tab_search)
        pane.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Facet sidebar (left)
        sidebar = ttk.LabelFrame(pane, text="Filters", width=180)
        sidebar.pack(side="left", fill="y", padx=(0, 8))
        sidebar.pack_propagate(False)
        self._sidebar = sidebar
        self._facet_widgets: dict[str, tk.Variable] = {}
        self._build_facet_sidebar()

        # Results area (right)
        result_outer = ttk.Frame(pane)
        result_outer.pack(side="left", fill="both", expand=True)

        self._results_canvas = tk.Canvas(result_outer, highlightthickness=0)
        vsb = ttk.Scrollbar(result_outer, orient="vertical",
                             command=self._results_canvas.yview)
        self._results_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._results_canvas.pack(side="left", fill="both", expand=True)

        self._results_inner = ttk.Frame(self._results_canvas)
        self._canvas_window = self._results_canvas.create_window(
            (0, 0), window=self._results_inner, anchor="nw"
        )
        self._results_inner.bind(
            "<Configure>",
            lambda _e: self._results_canvas.configure(
                scrollregion=self._results_canvas.bbox("all")
            ),
        )
        self._results_canvas.bind(
            "<Configure>",
            lambda e: self._results_canvas.itemconfig(self._canvas_window, width=e.width),
        )
        # Mouse-wheel scrolling
        self._results_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._results_canvas.yview_scroll(-1 * (e.delta // 120), "units"),
        )

    def _build_facet_sidebar(self) -> None:
        for widget in self._sidebar.winfo_children():
            widget.destroy()
        self._facet_widgets.clear()

        # Author filter
        ttk.Label(self._sidebar, text="Author").pack(anchor="w", padx=8, pady=(8, 2))
        author_var = tk.StringVar()
        author_entry = ttk.Entry(self._sidebar, textvariable=author_var, width=20)
        author_entry.pack(padx=8, fill="x")
        self._facet_widgets["author"] = author_var

        # Year filter
        ttk.Label(self._sidebar, text="Year").pack(anchor="w", padx=8, pady=(8, 2))
        year_var = tk.StringVar()
        ttk.Entry(self._sidebar, textvariable=year_var, width=20).pack(padx=8, fill="x")
        self._facet_widgets["year"] = year_var

        # File type filter
        ttk.Label(self._sidebar, text="File Type").pack(anchor="w", padx=8, pady=(8, 2))
        ftype_var = tk.StringVar()
        ftype_combo = ttk.Combobox(
            self._sidebar, textvariable=ftype_var,
            values=["", "pdf", "epub"], state="readonly", width=18
        )
        ftype_combo.pack(padx=8, fill="x")
        self._facet_widgets["fileType"] = ftype_var

        ttk.Button(
            self._sidebar, text="Apply Filters", command=self._apply_filters
        ).pack(padx=8, pady=8, fill="x")
        ttk.Button(
            self._sidebar, text="Clear Filters",
            command=self._clear_filters, style="Secondary.TButton"
        ).pack(padx=8, fill="x")

    def _apply_filters(self) -> None:
        self._filters = {
            k: v.get().strip()
            for k, v in self._facet_widgets.items()
            if v.get().strip()
        }
        self._run_search()

    def _clear_filters(self) -> None:
        for v in self._facet_widgets.values():
            v.set("")
        self._filters = {}
        self._run_search()

    def _run_search(self) -> None:
        query = self._search_var.get().strip()
        if not query:
            return
        self._search_status.set("Searching…")
        self._clear_result_cards()

        def _worker():
            response = do_search(query, filters=self._filters or None)
            self._queue.put(("search_done", response))

        threading.Thread(target=_worker, daemon=True).start()

    def _clear_search(self) -> None:
        self._search_var.set("")
        self._clear_result_cards()
        self._search_status.set("")

    def _clear_result_cards(self) -> None:
        for widget in self._results_inner.winfo_children():
            widget.destroy()

    def _display_results(self, response: SearchResponse) -> None:
        self._last_response = response
        self._clear_result_cards()
        self._refresh_history()

        count = len(response.results)
        intent_note = f" (intent: {response.query_intent})" if response.query_intent != "general" else ""
        fallback_note = " [fuzzy match]" if response.used_fallback else ""
        self._search_status.set(
            f"{count} result(s) from {response.total_candidates} candidates{intent_note}{fallback_note}"
        )

        if not response.results:
            ttk.Label(
                self._results_inner,
                text="No results found. Try different keywords or check your spelling.",
                foreground=self._pal["muted"],
            ).pack(pady=20)
            return

        pal = self._pal
        for i, r in enumerate(response.results):
            card = tk.Frame(
                self._results_inner,
                bg=pal["card_bg"],
                bd=0,
                highlightbackground=pal["border"],
                highlightthickness=1,
            )
            card.pack(fill="x", pady=4, padx=2)

            # Accent left border
            tk.Frame(card, bg=pal["result_left"], width=4).pack(side="left", fill="y")

            body = tk.Frame(card, bg=pal["card_bg"], padx=12, pady=8)
            body.pack(side="left", fill="both", expand=True)

            # Title row
            title_row = tk.Frame(body, bg=pal["card_bg"])
            title_row.pack(fill="x")
            tk.Label(
                title_row, text=r.title,
                font=("", 11, "bold"),
                bg=pal["card_bg"], fg=pal["fg"],
                anchor="w",
            ).pack(side="left")

            score_pct = f"{r.score * 100:.0f}%"
            tk.Label(
                title_row, text=score_pct,
                font=("", 9),
                bg=pal["card_bg"], fg=pal["score_fg"],
            ).pack(side="right")

            # Metadata row
            meta_parts = []
            if r.section_header:
                meta_parts.append(f"§ {r.section_header}")
            meta_parts.append(f"p. {r.page_num}")
            if r.author:
                meta_parts.append(r.author)
            if r.year:
                meta_parts.append(r.year)
            meta_parts.append(r.file_type.upper() if r.file_type else "")
            meta_text = "  ·  ".join(p for p in meta_parts if p)
            tk.Label(
                body, text=meta_text,
                font=("", 9),
                bg=pal["card_bg"], fg=pal["muted"],
                anchor="w",
            ).pack(fill="x")

            # Snippet
            snippet_lbl = tk.Label(
                body, text=r.snippet,
                font=("", 10),
                bg=pal["card_bg"], fg=pal["fg"],
                anchor="w", justify="left",
                wraplength=WINDOW_WIDTH - 260,
            )
            snippet_lbl.pack(fill="x", pady=(4, 0))

            # Open button
            btn_row = tk.Frame(body, bg=pal["card_bg"])
            btn_row.pack(fill="x", pady=(6, 0))
            _fp = r.file_path

            def _open_file(path=_fp):
                if os.path.exists(path):
                    if sys.platform == "win32":
                        os.startfile(path)
                    elif sys.platform == "darwin":
                        os.system(f'open "{path}"')
                    else:
                        os.system(f'xdg-open "{path}"')
                else:
                    show_error("Not found", f"File not found:\n{path}")

            ttk.Button(btn_row, text="Open file", command=_open_file,
                       style="Secondary.TButton").pack(side="left")

            # Copy citation
            citation = f"{r.title}, p. {r.page_num}"
            if r.author:
                citation = f"{r.author} — {citation}"

            def _copy(cit=citation):
                self.root.clipboard_clear()
                self.root.clipboard_append(cit)

            ttk.Button(btn_row, text="Copy citation", command=_copy,
                       style="Secondary.TButton").pack(side="left", padx=(6, 0))

        # Update facet sidebar with live counts
        self._update_facet_counts(response.facets)

    def _update_facet_counts(self, facets: dict) -> None:
        """Show live facet counts below the filter inputs."""
        for widget in self._sidebar.winfo_children():
            if isinstance(widget, ttk.Label) and getattr(widget, "_is_count", False):
                widget.destroy()

        def _count_label(parent, items):
            for item in items[:5]:
                lbl = ttk.Label(
                    parent,
                    text=f"  {item['name']} ({item['count']})",
                    foreground=self._pal["muted"],
                )
                lbl._is_count = True
                lbl.pack(anchor="w", padx=8)

    # ── Search history ────────────────────────────────────────────────────────
    def _refresh_history(self) -> None:
        hist = get_search_history()
        self._hist_combo["values"] = hist
        if hist:
            self._hist_combo.set(hist[0])

    def _use_history(self, _event=None) -> None:
        q = self._hist_var.get()
        if q:
            self._search_var.set(q)
            self._run_search()

    # ── Tools tab ─────────────────────────────────────────────────────────────
    def _build_tools_tab(self) -> None:
        frame = ttk.Frame(self._tab_tools, padding=20)
        frame.pack(fill="both", expand=True)

        # OCR section
        ocr_frame = ttk.LabelFrame(frame, text="OCR — Make Scanned PDFs Searchable")
        ocr_frame.pack(fill="x", pady=(0, 16))

        tess_ok = tesseract_available()
        tess_status = "✓ Tesseract found — OCR ready" if tess_ok else \
                      "✗ Tesseract not found — install from https://github.com/UB-Mannheim/tesseract/wiki"
        tess_color = "#22c55e" if tess_ok else "#ef4444"
        tk.Label(ocr_frame, text=tess_status, fg=tess_color,
                 bg=self._pal["frame_bg"]).pack(anchor="w", padx=8, pady=4)

        ttk.Label(
            ocr_frame,
            text="Select a scanned PDF and click 'Run OCR' to extract text.\n"
                 "The result is re-indexed and becomes searchable.",
            foreground=self._pal["muted"],
        ).pack(anchor="w", padx=8, pady=(0, 8))

        ocr_btn_row = ttk.Frame(ocr_frame)
        ocr_btn_row.pack(fill="x", padx=8, pady=(0, 8))
        self._ocr_path_var = tk.StringVar(value="No file selected")
        ttk.Label(ocr_btn_row, textvariable=self._ocr_path_var,
                  foreground=self._pal["muted"]).pack(side="left", fill="x", expand=True)

        ocr_state = "normal" if tess_ok else "disabled"
        ttk.Button(ocr_btn_row, text="Select PDF…", command=self._select_ocr_file).pack(side="left", padx=(6, 0))
        self._ocr_run_btn = ttk.Button(
            ocr_frame, text="Run OCR & Index", command=self._run_ocr, state=ocr_state
        )
        self._ocr_run_btn.pack(padx=8, pady=(0, 8), anchor="w")
        self._ocr_file: str = ""

        self._ocr_progress_var = tk.DoubleVar(value=0)
        self._ocr_progress = ttk.Progressbar(ocr_frame, variable=self._ocr_progress_var, maximum=100)

        self._ocr_status_var = tk.StringVar(value="")
        ttk.Label(ocr_frame, textvariable=self._ocr_status_var,
                  foreground=self._pal["muted"]).pack(padx=8, pady=(0, 8), anchor="w")

        # EPUB → PDF section
        epub_frame = ttk.LabelFrame(frame, text="EPUB → PDF Converter")
        epub_frame.pack(fill="x", pady=(0, 16))

        rl_ok = _HAS_REPORTLAB
        rl_status = "✓ reportlab found — conversion ready" if rl_ok else \
                    "✗ reportlab not installed — run: pip install reportlab"
        rl_color = "#22c55e" if rl_ok else "#ef4444"
        tk.Label(epub_frame, text=rl_status, fg=rl_color,
                 bg=self._pal["frame_bg"]).pack(anchor="w", padx=8, pady=4)

        ttk.Label(
            epub_frame,
            text="Convert an EPUB file to a simple searchable PDF.",
            foreground=self._pal["muted"],
        ).pack(anchor="w", padx=8, pady=(0, 8))

        epub_row = ttk.Frame(epub_frame)
        epub_row.pack(fill="x", padx=8, pady=(0, 8))
        self._epub_path_var = tk.StringVar(value="No file selected")
        ttk.Label(epub_row, textvariable=self._epub_path_var,
                  foreground=self._pal["muted"]).pack(side="left", fill="x", expand=True)
        ttk.Button(epub_row, text="Select EPUB…", command=self._select_epub_file).pack(side="left", padx=(6, 0))

        epub_state = "normal" if rl_ok else "disabled"
        self._epub_convert_btn = ttk.Button(
            epub_frame, text="Convert & Save PDF", command=self._run_epub_convert, state=epub_state
        )
        self._epub_convert_btn.pack(padx=8, pady=(0, 8), anchor="w")
        self._epub_file: str = ""

        self._epub_status_var = tk.StringVar(value="")
        ttk.Label(epub_frame, textvariable=self._epub_status_var,
                  foreground=self._pal["muted"]).pack(padx=8, pady=(0, 8), anchor="w")

    def _select_ocr_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select scanned PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._ocr_file = path
            self._ocr_path_var.set(os.path.basename(path))

    def _run_ocr(self) -> None:
        if not self._ocr_file:
            show_error("No file", "Please select a PDF file first.")
            return
        self._ocr_progress.pack(fill="x", padx=8, pady=(0, 4))
        self._ocr_progress_var.set(0)
        self._ocr_status_var.set("Running OCR…")
        self._ocr_run_btn.configure(state="disabled")

        def _worker():
            def _cb(fp, fi, ft, pg, pgt):
                pct = pg / max(pgt, 1) * 100
                self._queue.put(("ocr_progress", f"OCR page {pg}/{pgt}", pct))

            result = index_paths([self._ocr_file], ocr=True, progress_cb=_cb)
            self._queue.put(("ocr_done", result))

        threading.Thread(target=_worker, daemon=True).start()

    def _select_epub_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select EPUB file",
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")],
        )
        if path:
            self._epub_file = path
            self._epub_path_var.set(os.path.basename(path))

    def _run_epub_convert(self) -> None:
        if not self._epub_file:
            show_error("No file", "Please select an EPUB file first.")
            return
        save_path = filedialog.asksaveasfilename(
            title="Save PDF as…",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=os.path.splitext(os.path.basename(self._epub_file))[0] + ".pdf",
        )
        if not save_path:
            return
        self._epub_status_var.set("Converting…")
        self._epub_convert_btn.configure(state="disabled")

        def _worker():
            ok, msg = epub_to_pdf(self._epub_file, save_path)
            self._queue.put(("epub_done", ok, msg, save_path))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Theme toggle ──────────────────────────────────────────────────────────
    def _toggle_theme(self) -> None:
        self._dark = not self._dark
        self._pal = apply_theme(self.root, self._dark)

    # ── Keyboard shortcuts ────────────────────────────────────────────────────
    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-f>", lambda _e: self._focus_search())
        self.root.bind_all("<Control-F>", lambda _e: self._focus_search())
        self.root.bind_all("<Control-o>", lambda _e: self._add_files())
        self.root.bind_all("<Control-O>", lambda _e: self._add_files())
        self.root.bind_all("<Control-d>", lambda _e: self._toggle_theme())
        self.root.bind_all("<Control-D>", lambda _e: self._toggle_theme())
        self.root.bind_all("<Escape>", lambda _e: self._clear_search())

    def _focus_search(self) -> None:
        self._notebook.select(1)  # switch to Search tab
        self._search_entry.focus_set()

    # ── Queue polling (main-thread safe message bridge) ───────────────────────
    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _handle_message(self, msg) -> None:
        kind = msg[0]

        if kind == "progress":
            _, text, pct = msg
            self._lib_status.set(text)
            self._lib_progress_var.set(pct)

        elif kind == "index_done":
            _, result = msg
            self._lib_progress.pack_forget()
            idx = result["indexed"]
            skp = result["skipped"]
            fail = result["failed"]
            self._lib_status.set(f"Done: {idx} indexed, {skp} skipped, {fail} failed")
            self._refresh_library()
            self._refresh_history()
            if result["errors"]:
                show_error(
                    "Some files failed",
                    "\n".join(result["errors"][:10]),
                )

        elif kind == "search_done":
            _, response = msg
            self._display_results(response)

        elif kind == "ocr_progress":
            _, text, pct = msg
            self._ocr_status_var.set(text)
            self._ocr_progress_var.set(pct)

        elif kind == "ocr_done":
            _, result = msg
            self._ocr_progress.pack_forget()
            self._ocr_run_btn.configure(state="normal")
            idx = result["indexed"]
            fail = result["failed"]
            if idx:
                self._ocr_status_var.set(f"✓ OCR complete — {idx} file(s) indexed.")
                self._refresh_library()
            else:
                self._ocr_status_var.set(f"✗ OCR failed: {'; '.join(result['errors'])}")

        elif kind == "epub_done":
            _, ok, msg_text, save_path = msg
            self._epub_convert_btn.configure(state="normal")
            if ok:
                self._epub_status_var.set(f"✓ Saved: {save_path}")
                if ask_yes_no("Saved", f"PDF saved.\nAdd it to the library for searching?"):
                    self._start_indexing([save_path])
            else:
                self._epub_status_var.set(f"✗ {msg_text}")
