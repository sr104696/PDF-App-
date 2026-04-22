"""
Application entry point. Sets up Tkinter (with optional DnD), indexer, searcher, and UI.
"""
import os
import tkinter as tk

# Optional dark-theme bootstrap
try:
    import ttkbootstrap as ttk
    HAS_BOOTSTRAP = True
except Exception:
    HAS_BOOTSTRAP = False

# Optional drag-and-drop root
try:
    from tkinterdnd2 import TkinterDnD
    ROOT_CLS = TkinterDnD.Tk
except Exception:
    ROOT_CLS = tk.Tk

from indexer import Indexer
from searcher import Searcher
from ui import PDFSearcherUI

def main():
    os.makedirs("data", exist_ok=True)
    db_path = os.path.join("data", "pdf_searcher.db")

    indexer = Indexer(db_path)
    searcher = Searcher(indexer)

    root = ROOT_CLS()
    if HAS_BOOTSTRAP:
        style = ttk.Style(theme="flatly")
    app = PDFSearcherUI(root, indexer, searcher)
    root.mainloop()

if __name__ == "__main__":
    main()
