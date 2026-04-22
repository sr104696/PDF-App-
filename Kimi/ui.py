"""
Tkinter UI with ttkbootstrap theming, drag-drop, facets, and threaded ops.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    HAS_BOOTSTRAP = True
except Exception:
    from tkinter import ttk
    HAS_BOOTSTRAP = False

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False

from indexer import Indexer
from searcher import Searcher, SearchResult
import utils

class PDFSearcherUI:
    def __init__(self, root: tk.Tk, indexer: Indexer, searcher: Searcher):
        self.root = root
        self.indexer = indexer
        self.searcher = searcher
        self.dark_mode = False
        self.active_filters: dict = {}
        self._progress_win = None

        self._setup_window()
        self._build_ui()
        self._bind_shortcuts()
        self._load_library()

    # -----------------------------------------------------------------------
    # Window setup
    # -----------------------------------------------------------------------
    def _setup_window(self):
        self.root.title("PDF Intelligence")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

    # -----------------------------------------------------------------------
    # Build UI
    # -----------------------------------------------------------------------
    def _build_ui(self):
        # Header
        hdr = ttk.Frame(self.root, padding=10)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="PDF Intelligence", font=("Segoe UI", 18, "bold")).pack(side="left")
        self.btn_theme = ttk.Button(hdr, text="Dark Mode", command=self._toggle_theme)
        self.btn_theme.pack(side="right")

        # Notebook
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=5)

        # --- Library ---
        self.frm_lib = ttk.Frame(self.nb)
        self.nb.add(self.frm_lib, text="Library")
        self._build_library()

        # --- Search ---
        self.frm_search = ttk.Frame(self.nb)
        self.nb.add(self.frm_search, text="Search")
        self._build_search()

        # --- Tools ---
        self.frm_tools = ttk.Frame(self.nb)
        self.nb.add(self.frm_tools, text="Tools")
        self._build_tools()

    def _build_library(self):
        dz = ttk.LabelFrame(self.frm_lib, text="Add Documents", padding=20)
        dz.pack(fill="x", padx=10, pady=10)

        self.lbl_drop = ttk.Label(dz, text="Drag & Drop PDF/EPUB files here\nor click to browse",
                                  justify="center", font=("Segoe UI", 12))
        self.lbl_drop.pack(pady=20)
        self.lbl_drop.bind("<Button-1>", lambda e: self._browse_files())

        if HAS_DND and hasattr(self.lbl_drop, 'drop_target_register'):
            self.lbl_drop.drop_target_register(DND_FILES)
            self.lbl_drop.dnd_bind('<<Drop>>', self._on_drop)

        ttk.Button(dz, text="Browse...", command=self._browse_files).pack(pady=5)

        cols = ("Title", "Author", "Pages", "Type", "Indexed")
        self.tree_lib = ttk.Treeview(self.frm_lib, columns=cols, show="headings", height=15)
        for c in cols:
            self.tree_lib.heading(c, text=c)
            self.tree_lib.column(c, width=150)
        self.tree_lib.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_search(self):
        top = ttk.Frame(self.frm_search, padding=10)
        top.pack(fill="x")

        self.var_query = tk.StringVar()
        self.ent_query = ttk.Entry(top, textvariable=self.var_query, font=("Segoe UI", 12))
        self.ent_query.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.ent_query.bind("<Return>", lambda e: self._do_search())

        ttk.Button(top, text="Search", command=self._do_search).pack(side="left")

        paned = ttk.PanedWindow(self.frm_search, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        # Facet sidebar
        self.frm_facets = ttk.LabelFrame(paned, text="Filters", width=220)
        paned.add(self.frm_facets, weight=0)
        self.inner_facets = ttk.Frame(self.frm_facets)
        self.inner_facets.pack(fill="both", expand=True)

        # Results
        rcontainer = ttk.Frame(paned)
        paned.add(rcontainer, weight=1)

        self.can_results = tk.Canvas(rcontainer)
        vsb = ttk.Scrollbar(rcontainer, orient="vertical", command=self.can_results.yview)
        self.can_results.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.can_results.pack(side="left", fill="both", expand=True)

        self.frm_results = ttk.Frame(self.can_results)
        self.can_results.create_window((0, 0), window=self.frm_results, anchor="nw")
        self.frm_results.bind("<Configure>", lambda e: self.can_results.configure(
            scrollregion=self.can_results.bbox("all"), width=e.width))

        # Clear filters link
        ttk.Button(self.frm_facets, text="Clear Filters", command=self._clear_filters).pack(fill="x", padx=5, pady=5)

    def _build_tools(self):
        f = ttk.LabelFrame(self.frm_tools, text="OCR & Conversion", padding=20)
        f.pack(fill="x", padx=10, pady=10)

        ttk.Label(f, text="Make Scanned PDF Searchable", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(f, text="Extract text from image-based PDFs using Tesseract OCR").pack(anchor="w", pady=2)
        ttk.Button(f, text="Select PDF for OCR…", command=self._run_ocr).pack(anchor="w", pady=5)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=15)

        ttk.Label(f, text="EPUB → Text", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(f, text="Extract and save EPUB chapters as plain text").pack(anchor="w", pady=2)
        ttk.Button(f, text="Select EPUB…", command=self._extract_epub).pack(anchor="w", pady=5)

    # -----------------------------------------------------------------------
    # Shortcuts
    # -----------------------------------------------------------------------
    def _bind_shortcuts(self):
        self.root.bind("<Control-f>", lambda e: self.ent_query.focus_set())
        self.root.bind("<Control-o>", lambda e: self._browse_files())
        self.root.bind("<Escape>", lambda e: (self.var_query.set(""), self._clear_filters()))

    # -----------------------------------------------------------------------
    # Theme
    # -----------------------------------------------------------------------
    def _toggle_theme(self):
        if not HAS_BOOTSTRAP:
            messagebox.showinfo("Theme", "ttkbootstrap not installed.")
            return
        self.dark_mode = not self.dark_mode
        style = ttk.Style()
        style.theme_use("darkly" if self.dark_mode else "flatly")
        self.btn_theme.configure(text="Light Mode" if self.dark_mode else "Dark Mode")

    # -----------------------------------------------------------------------
    # Library / Drag-Drop
    # -----------------------------------------------------------------------
    def _browse_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Documents", "*.pdf *.epub")])
        if files:
            self._index_files(list(files))

    def _on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        self._index_files([f for f in files if f.lower().endswith((".pdf", ".epub"))])

    def _index_files(self, files: list):
        def task():
            total = len(files)
            for i, f in enumerate(files):
                self._show_progress(f"Indexing {os.path.basename(f)}…", int((i / total) * 100))
                self.indexer.index_document(f)
            self._hide_progress()
            self.root.after(0, self._load_library)

        threading.Thread(target=task, daemon=True).start()

    def _load_library(self):
        for item in self.tree_lib.get_children():
            self.tree_lib.delete(item)
        cur = self.indexer.conn.execute(
            "SELECT title,author,pageCount,fileType,indexedAt FROM documents ORDER BY indexedAt DESC")
        for row in cur:
            self.tree_lib.insert("", "end", values=row)

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------
    def _do_search(self):
        query = self.var_query.get().strip()
        if not query:
            return
        for w in self.frm_results.winfo_children():
            w.destroy()

        def task():
            results, facets = self.searcher.search(query, filters=self.active_filters)
            self.root.after(0, lambda: self._render_results(results, facets))

        threading.Thread(target=task, daemon=True).start()

    def _render_results(self, results: list, facets: dict):
        # Facets
        for w in self.inner_facets.winfo_children():
            w.destroy()

        for name, values in facets.items():
            if not values:
                continue
            frm = ttk.LabelFrame(self.inner_facets, text=name.title())
            frm.pack(fill="x", pady=4, padx=5)
            for val, cnt in sorted(values.items(), key=lambda x: -x[1])[:12]:
                lbl = ttk.Label(frm, text=f"{val}  ({cnt})", foreground="#0066cc", cursor="hand2")
                lbl.pack(anchor="w", padx=5, pady=1)
                lbl.bind("<Button-1>", lambda e, v=val, n=name: self._apply_facet(n, v))

        # Results
        if not results:
            ttk.Label(self.frm_results, text="No results found.").pack(pady=20)
            return

        for r in results:
            card = ttk.Frame(self.frm_results, relief="ridge", padding=10)
            card.pack(fill="x", pady=5, padx=5)

            ttk.Label(card, text=r.title, font=("Segoe UI", 12, "bold")).pack(anchor="w")
            ttk.Label(card, text=f"Page {r.page_num}  |  {r.citation}", foreground="gray").pack(anchor="w")
            ttk.Label(card, text=r.snippet, wraplength=750, justify="left").pack(anchor="w", pady=5)

            bf = ttk.Frame(card)
            bf.pack(anchor="w")
            ttk.Button(bf, text="Copy Citation", command=lambda c=r.citation: self._copy(c)).pack(side="left", padx=2)
            ttk.Button(bf, text="Open File", command=lambda p=r.file_path: utils.open_file(p)).pack(side="left", padx=2)

    def _apply_facet(self, name: str, value: str):
        self.active_filters[name] = value
        self._do_search()

    def _clear_filters(self):
        self.active_filters.clear()
        self._do_search()

    def _copy(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # -----------------------------------------------------------------------
    # Progress
    # -----------------------------------------------------------------------
    def _show_progress(self, msg: str, pct: int):
        def ui():
            if self._progress_win is None or not self._progress_win.winfo_exists():
                self._progress_win = tk.Toplevel(self.root)
                self._progress_win.title("Processing")
                self._progress_win.geometry("400x120")
                self._progress_win.transient(self.root)
                self._progress_win.grab_set()
                self._prog_msg = tk.StringVar()
                ttk.Label(self._progress_win, textvariable=self._prog_msg).pack(pady=10)
                self._prog_bar = ttk.Progressbar(self._progress_win, length=350, mode="determinate")
                self._prog_bar.pack(pady=5)
            self._prog_msg.set(msg)
            self._prog_bar["value"] = pct
            self._progress_win.update_idletasks()
        self.root.after(0, ui)

    def _hide_progress(self):
        def ui():
            if self._progress_win and self._progress_win.winfo_exists():
                self._progress_win.destroy()
                self._progress_win = None
        self.root.after(0, ui)

    # -----------------------------------------------------------------------
    # Tools
    # -----------------------------------------------------------------------
    def _run_ocr(self):
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return

        def task():
            self._show_progress("Running OCR…", 0)
            try:
                from pdf_parser import ocr_pdf
                pages = ocr_pdf(f, progress_callback=lambda m, p: self._show_progress(m, p))
                out = f.replace(".pdf", "_searchable.txt")
                with open(out, "w", encoding="utf-8") as fh:
                    fh.write("\n\n--- Page Break ---\n\n".join(pages))
                self._hide_progress()
                messagebox.showinfo("OCR Complete", f"Saved to:\n{out}")
            except Exception as exc:
                self._hide_progress()
                messagebox.showerror("OCR Error", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _extract_epub(self):
        f = filedialog.askopenfilename(filetypes=[("EPUB", "*.epub")])
        if not f:
            return
        try:
            from pdf_parser import extract_epub_text
            chapters, meta = extract_epub_text(f)
            out = f.replace(".epub", "_extracted.txt")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(f"Title: {meta.get('title','')}\n")
                fh.write(f"Author: {meta.get('author','')}\n\n")
                for i, ch in enumerate(chapters, 1):
                    fh.write(f"\n\n=== Chapter {i} ===\n\n")
                    fh.write(ch)
            messagebox.showinfo("Extraction Complete", f"Saved to:\n{out}")
        except Exception as exc:
            messagebox.showerror("Extraction Error", str(exc))
