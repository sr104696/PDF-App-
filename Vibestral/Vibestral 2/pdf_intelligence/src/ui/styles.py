# src/ui/styles.py
# Changes: Used Claude's richer palette (more keys: card_bg, frame_bg, entry_bg,
# result_left, score_fg, etc.) needed by app_ui.py; fixed mojibake.
"""ttk styles for light and dark mode. No external theme packs."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

LIGHT = {
    "bg":          "#f5f5f5",
    "frame_bg":    "#f5f5f5",
    "card_bg":     "#ffffff",
    "entry_bg":    "#ffffff",
    "fg":          "#1a1a1a",
    "muted":       "#6b7280",
    "accent":      "#2563eb",
    "accent_fg":   "#ffffff",
    "border":      "#d1d5db",
    "result_left": "#2563eb",
    "score_fg":    "#9ca3af",
    "row_alt":     "#f3f4f6",
    "select":      "#dbeafe",
    "progress_bg": "#e5e7eb",
    "progress_fg": "#2563eb",
}

DARK = {
    "bg":          "#1e1e2e",
    "frame_bg":    "#1e1e2e",
    "card_bg":     "#2a2a3e",
    "entry_bg":    "#313145",
    "fg":          "#cdd6f4",
    "muted":       "#a6adc8",
    "accent":      "#89b4fa",
    "accent_fg":   "#1e1e2e",
    "border":      "#45475a",
    "result_left": "#89b4fa",
    "score_fg":    "#6c7086",
    "row_alt":     "#242430",
    "select":      "#1e3a5f",
    "progress_bg": "#313145",
    "progress_fg": "#89b4fa",
}


def apply(root: tk.Tk, mode: str = "light") -> dict:
    """Apply theme and return the active palette dict."""
    pal = DARK if mode == "dark" else LIGHT
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.configure(bg=pal["bg"])

    style.configure(".",
        background=pal["frame_bg"],
        foreground=pal["fg"],
        fieldbackground=pal["entry_bg"],
        bordercolor=pal["border"],
        troughcolor=pal["progress_bg"],
        selectbackground=pal["accent"],
        selectforeground=pal["accent_fg"],
    )
    style.configure("TFrame",   background=pal["frame_bg"])
    style.configure("TLabel",   background=pal["frame_bg"], foreground=pal["fg"])
    style.configure("Muted.TLabel",   background=pal["frame_bg"], foreground=pal["muted"])
    style.configure("Title.TLabel",   background=pal["frame_bg"], foreground=pal["fg"],
                    font=("Segoe UI", 16, "bold"))
    style.configure("Heading.TLabel", background=pal["card_bg"],  foreground=pal["fg"],
                    font=("Segoe UI", 11, "bold"))
    style.configure("Snippet.TLabel", background=pal["card_bg"],  foreground=pal["fg"],
                    font=("Segoe UI", 10), wraplength=900)
    style.configure("Card.TFrame",    background=pal["card_bg"])

    style.configure("TNotebook", background=pal["bg"], borderwidth=0)
    style.configure("TNotebook.Tab",
        background=pal["bg"], foreground=pal["muted"], padding=[12, 6])
    style.map("TNotebook.Tab",
        background=[("selected", pal["card_bg"])],
        foreground=[("selected", pal["accent"])],
    )
    style.configure("TEntry",
        fieldbackground=pal["entry_bg"], foreground=pal["fg"],
        bordercolor=pal["border"], insertcolor=pal["fg"])
    style.configure("TButton",
        background=pal["accent"], foreground=pal["accent_fg"],
        borderwidth=0, padding=[10, 5], relief="flat")
    style.map("TButton",
        background=[("active", pal["result_left"]), ("disabled", pal["border"])])
    style.configure("Secondary.TButton",
        background=pal["border"], foreground=pal["fg"],
        borderwidth=0, padding=[8, 4], relief="flat")
    style.configure("Accent.TButton",
        background=pal["accent"], foreground=pal["accent_fg"],
        borderwidth=0, padding=[10, 6], relief="flat")
    style.configure("TProgressbar",
        troughcolor=pal["progress_bg"], background=pal["progress_fg"],
        borderwidth=0, thickness=6)
    style.configure("TScrollbar",
        background=pal["border"], troughcolor=pal["frame_bg"], arrowcolor=pal["muted"])
    style.configure("TCombobox",
        fieldbackground=pal["entry_bg"], foreground=pal["fg"], background=pal["entry_bg"])
    style.configure("TLabelframe",
        background=pal["frame_bg"], foreground=pal["muted"], bordercolor=pal["border"])
    style.configure("TLabelframe.Label",
        background=pal["frame_bg"], foreground=pal["muted"])
    style.configure("Treeview",
        background=pal["card_bg"], foreground=pal["fg"],
        fieldbackground=pal["card_bg"], rowheight=24, bordercolor=pal["border"])
    style.configure("Treeview.Heading",
        background=pal["bg"], foreground=pal["fg"], font=("Segoe UI", 9, "bold"))
    style.map("Treeview",
        background=[("selected", pal["select"])],
        foreground=[("selected", pal["fg"])])

    return pal
