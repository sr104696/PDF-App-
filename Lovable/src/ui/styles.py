"""ttk styles for light & dark mode. Tiny — no external theme packs."""
from __future__ import annotations

from tkinter import ttk

LIGHT = {
    "bg": "#fafafa", "fg": "#1a1a1a", "muted": "#666666",
    "accent": "#2563eb", "card": "#ffffff", "border": "#e5e7eb",
    "row_alt": "#f3f4f6", "select": "#dbeafe",
}
DARK = {
    "bg": "#1e1e1e", "fg": "#e8e8e8", "muted": "#9aa0a6",
    "accent": "#60a5fa", "card": "#262626", "border": "#3a3a3a",
    "row_alt": "#242424", "select": "#1e3a5f",
}


def apply(root, mode: str = "light") -> dict:
    palette = DARK if mode == "dark" else LIGHT
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.configure(bg=palette["bg"])
    base = {"background": palette["bg"], "foreground": palette["fg"]}

    style.configure("TFrame", **base)
    style.configure("Card.TFrame", background=palette["card"])
    style.configure("TLabel", **base)
    style.configure("Muted.TLabel", background=palette["bg"],
                    foreground=palette["muted"])
    style.configure("Title.TLabel", background=palette["bg"],
                    foreground=palette["fg"], font=("Segoe UI", 16, "bold"))
    style.configure("Heading.TLabel", background=palette["card"],
                    foreground=palette["fg"], font=("Segoe UI", 11, "bold"))
    style.configure("Snippet.TLabel", background=palette["card"],
                    foreground=palette["fg"], font=("Segoe UI", 10), wraplength=900)

    style.configure("TButton", padding=6)
    style.configure("Accent.TButton", padding=8, foreground="#ffffff",
                    background=palette["accent"])
    style.map("Accent.TButton",
              background=[("active", palette["accent"])])

    style.configure("TEntry", fieldbackground=palette["card"],
                    foreground=palette["fg"], insertcolor=palette["fg"])
    style.configure("Treeview", background=palette["card"],
                    foreground=palette["fg"], fieldbackground=palette["card"],
                    rowheight=24, bordercolor=palette["border"])
    style.configure("Treeview.Heading", background=palette["bg"],
                    foreground=palette["fg"], font=("Segoe UI", 9, "bold"))
    style.map("Treeview", background=[("selected", palette["select"])],
              foreground=[("selected", palette["fg"])])

    style.configure("TNotebook", background=palette["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 6), background=palette["bg"],
                    foreground=palette["fg"])
    style.map("TNotebook.Tab",
              background=[("selected", palette["card"])])

    return palette
