"""Simple dialogs used by the app."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Optional


def ask_open_files(parent: tk.Widget) -> List[str]:
    return list(filedialog.askopenfilenames(
        parent=parent,
        title="Add PDF / EPUB files",
        filetypes=[("PDF files", "*.pdf"), ("EPUB files", "*.epub"),
                   ("All supported", "*.pdf *.epub"), ("All files", "*.*")],
    ))


def ask_open_folder(parent: tk.Widget) -> Optional[str]:
    return filedialog.askdirectory(parent=parent, title="Add folder of PDFs/EPUBs") or None


def show_error(title: str, message: str) -> None:
    messagebox.showerror(title, message)


def show_info(title: str, message: str) -> None:
    messagebox.showinfo(title, message)


def show_text_popup(parent: tk.Widget, title: str, text: str) -> None:
    """Show a scrollable text popup (for embedding instructions, debug info, etc.)"""
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("640x400")
    win.resizable(True, True)
    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    sb = ttk.Scrollbar(frame)
    sb.pack(side="right", fill="y")
    txt = tk.Text(frame, wrap="word", yscrollcommand=sb.set, font=("Consolas", 10))
    txt.pack(side="left", fill="both", expand=True)
    sb.config(command=txt.yview)
    txt.insert("end", text)
    txt.config(state="disabled")
    ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))
