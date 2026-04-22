# src/ui/dialogs.py
# Changes: Used Claude's version which has ProgressDialog and AboutDialog classes;
# fixed all mojibake in string literals.
"""Reusable modal dialogs."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..utils.constants import APP_NAME, APP_VERSION


def show_info(title: str, message: str) -> None:
    messagebox.showinfo(title, message)


def show_error(title: str, message: str) -> None:
    messagebox.showerror(title, message)


def ask_yes_no(title: str, message: str) -> bool:
    return messagebox.askyesno(title, message)


def about(parent: tk.Tk) -> None:
    AboutDialog(parent)


class ProgressDialog(tk.Toplevel):
    """Non-blocking progress dialog for long operations."""

    def __init__(self, parent: tk.Tk, title: str = "Working\u2026") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent close

        self._msg_var  = tk.StringVar(value="Starting\u2026")
        self._prog_var = tk.DoubleVar(value=0.0)

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, textvariable=self._msg_var, wraplength=340).pack(pady=(0, 10))
        self._bar = ttk.Progressbar(frame, variable=self._prog_var, maximum=100, length=340)
        self._bar.pack(pady=(0, 5))
        self._pct_lbl = ttk.Label(frame, text="0 %")
        self._pct_lbl.pack()

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")

    def update_progress(self, message: str, value: float) -> None:
        """value is 0-100."""
        self._msg_var.set(message)
        self._prog_var.set(value)
        self._pct_lbl.configure(text=f"{int(value)} %")
        self.update_idletasks()

    def close(self) -> None:
        self.grab_release()
        self.destroy()


class AboutDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title(f"About {APP_NAME}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack()
        ttk.Label(frame, text=f"v{APP_VERSION} \u2014 Offline Semantic Search").pack(pady=4)
        ttk.Label(
            frame,
            text=(
                "BM25 + FTS5 + Snowball stemming.\n"
                "No internet. No AI APIs. No telemetry.\n\n"
                "MIT License"
            ),
            justify="center",
        ).pack()
        ttk.Button(frame, text="Close", command=self.destroy).pack(pady=(16, 0))

        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
