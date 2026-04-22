"""Theme definitions for light and dark modes."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict


THEMES: Dict[str, Dict] = {
    "light": {
        "bg":           "#F8F9FA",
        "panel_bg":     "#FFFFFF",
        "sidebar_bg":   "#F1F3F5",
        "accent":       "#2E75B6",
        "accent2":      "#17788D",
        "text":         "#1A1A2E",
        "text_muted":   "#6C757D",
        "border":       "#DEE2E6",
        "result_bg":    "#FFFFFF",
        "result_hover": "#EBF3FC",
        "snippet_bg":   "#F8F9FA",
        "tag_bg":       "#E3F0FB",
        "tag_fg":       "#1F5F8B",
        "score_fg":     "#17788D",
        "intent_bg":    "#FFF3CD",
        "intent_fg":    "#856404",
        "sem_on":       "#198754",
        "sem_off":      "#6C757D",
        "entry_bg":     "#FFFFFF",
        "select_bg":    "#B8D9F5",
    },
    "dark": {
        "bg":           "#1A1A2E",
        "panel_bg":     "#16213E",
        "sidebar_bg":   "#0F3460",
        "accent":       "#4DA6FF",
        "accent2":      "#45D1C0",
        "text":         "#E8EAF0",
        "text_muted":   "#9EA7B8",
        "border":       "#2D3A4F",
        "result_bg":    "#16213E",
        "result_hover": "#1E2D4A",
        "snippet_bg":   "#1A2540",
        "tag_bg":       "#1E3558",
        "tag_fg":       "#7DB8E8",
        "score_fg":     "#45D1C0",
        "intent_bg":    "#3D3010",
        "intent_fg":    "#FFD966",
        "sem_on":       "#28A745",
        "sem_off":      "#6C757D",
        "entry_bg":     "#0D1B2A",
        "select_bg":    "#1F4068",
    },
}

_current_theme = "light"


def current() -> Dict:
    return THEMES[_current_theme]


def toggle() -> str:
    global _current_theme
    _current_theme = "dark" if _current_theme == "light" else "light"
    return _current_theme


def apply(root: tk.Tk, style: ttk.Style) -> None:
    t = current()
    style.theme_use("clam")
    style.configure(".", background=t["bg"], foreground=t["text"],
                    font=("Segoe UI", 10))
    style.configure("TFrame",       background=t["bg"])
    style.configure("Panel.TFrame", background=t["panel_bg"])
    style.configure("Sidebar.TFrame", background=t["sidebar_bg"])
    style.configure("TLabel",       background=t["bg"], foreground=t["text"])
    style.configure("Muted.TLabel", background=t["bg"], foreground=t["text_muted"])
    style.configure("Panel.TLabel", background=t["panel_bg"], foreground=t["text"])
    style.configure("Sidebar.TLabel", background=t["sidebar_bg"], foreground=t["text"])
    style.configure("Accent.TLabel", background=t["bg"], foreground=t["accent"],
                    font=("Segoe UI", 10, "bold"))
    style.configure("TButton", background=t["accent"], foreground=t["panel_bg"],
                    borderwidth=0, focusthickness=0, relief="flat",
                    font=("Segoe UI", 10))
    style.map("TButton",
              background=[("active", t["accent2"]), ("pressed", t["accent2"])],
              foreground=[("active", "#FFFFFF")])
    style.configure("Ghost.TButton", background=t["bg"], foreground=t["accent"],
                    borderwidth=1, relief="flat")
    style.configure("TEntry", fieldbackground=t["entry_bg"], foreground=t["text"],
                    borderwidth=1, relief="flat", padding=4)
    style.configure("TCombobox", fieldbackground=t["entry_bg"], foreground=t["text"])
    style.configure("TNotebook", background=t["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=t["sidebar_bg"], foreground=t["text"],
                    padding=[12, 5], font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", t["panel_bg"])],
              foreground=[("selected", t["accent"])])
    style.configure("Treeview", background=t["panel_bg"], foreground=t["text"],
                    fieldbackground=t["panel_bg"], rowheight=26,
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading", background=t["sidebar_bg"],
                    foreground=t["text"], font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", t["select_bg"])])
    style.configure("TScrollbar", background=t["sidebar_bg"],
                    troughcolor=t["bg"], borderwidth=0)
    style.configure("Horizontal.TProgressbar",
                    background=t["accent"], troughcolor=t["border"])
    root.configure(bg=t["bg"])
