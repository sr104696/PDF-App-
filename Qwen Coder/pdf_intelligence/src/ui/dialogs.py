"""
Dialogs Module - Unchanged from original.
"""
from tkinter import messagebox


def show_info(title: str, message: str) -> None:
    """
    Show an information dialog.
    
    Args:
        title: Dialog title.
        message: Dialog message.
    """
    messagebox.showinfo(title, message)


def show_error(title: str, message: str) -> None:
    """
    Show an error dialog.
    
    Args:
        title: Dialog title.
        message: Dialog message.
    """
    messagebox.showerror(title, message)


def ask_yes_no(title: str, message: str) -> bool:
    """
    Show a yes/no dialog.
    
    Args:
        title: Dialog title.
        message: Dialog message.
        
    Returns:
        True if user clicked Yes, False otherwise.
    """
    return messagebox.askyesno(title, message)
