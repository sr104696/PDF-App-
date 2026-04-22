"""
Styles Module - Unchanged from original.
"""
from tkinter import ttk


def apply_theme(root, is_dark: bool = False) -> None:
    """
    Apply a theme to the application.
    
    Args:
        root: The Tkinter root window.
        is_dark: Whether to use dark theme.
    """
    style = ttk.Style(root)
    if is_dark:
        style.theme_use('clam')
        style.configure('.', background='#2d2d2d', foreground='white')
        style.configure('TFrame', background='#2d2d2d')
        style.configure('TLabel', background='#2d2d2d', foreground='white')
        style.configure('TButton', background='#404040', foreground='white')
        style.configure('TEntry', fieldbackground='#404040', foreground='white')
        root.configure(bg='#2d2d2d')
    else:
        style.theme_use('clam')
        style.configure('.', background='#f0f0f0', foreground='black')
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabel', background='#f0f0f0', foreground='black')
        style.configure('TButton', background='#e0e0e0', foreground='black')
        style.configure('TEntry', fieldbackground='white', foreground='black')
        root.configure(bg='#f0f0f0')
