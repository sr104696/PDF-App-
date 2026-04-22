"""Small modal dialogs (about, confirmations)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..utils.constants import APP_NAME, APP_VERSION


def about(parent) -> None:
    win = tk.Toplevel(parent)
    win.title(f"About {APP_NAME}")
    win.transient(parent)
    win.resizable(False, False)
    frm = ttk.Frame(win, padding=24)
    frm.pack()
    ttk.Label(frm, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
    ttk.Label(frm, text=f"Version {APP_VERSION}", style="Muted.TLabel").pack(anchor="w")
    ttk.Label(
        frm,
        text=("Offline PDF & EPUB intelligence with BM25 search.\n"
              "No internet. No cloud. No telemetry."),
        style="TLabel", justify="left",
    ).pack(anchor="w", pady=(12, 0))
    ttk.Button(frm, text="Close", command=win.destroy).pack(anchor="e", pady=(16, 0))
