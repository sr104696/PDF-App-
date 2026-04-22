"""
UI Application Module - Optimized version with improved thread safety.
"""
import tkinter as tk
from tkinter import ttk, filedialog
import threading
import os
from typing import Optional

from src.ui.styles import apply_theme
from src.ui.dialogs import show_info, show_error
from src.index.indexer import index_file
from src.search.searcher import execute_search
from src.index.schema import initialize_db


class AppUI:
    """Main application UI class."""
    
    def __init__(self, root: tk.Tk):
        """
        Initialize the application UI.
        
        Args:
            root: The main Tkinter window.
        """
        self.root = root
        self.root.title("PDF Intelligence Offline")
        self.root.geometry("800x600")
        
        self.is_dark = False
        self.results_text: Optional[tk.Text] = None
        self.search_var: Optional[tk.StringVar] = None
        self.status_var: Optional[tk.StringVar] = None
        self.notebook: Optional[ttk.Notebook] = None
        
        apply_theme(self.root, self.is_dark)
        
        initialize_db()
        
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Set up the main UI components."""
        # Top Bar
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(top_bar, text="Toggle Theme", command=self.toggle_theme).pack(side='right')
        
        # Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        # Tabs
        self.search_tab = ttk.Frame(self.notebook)
        self.library_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.search_tab, text="Search")
        self.notebook.add(self.library_tab, text="Library")
        
        self.build_search_tab()
        self.build_library_tab()
    
    def toggle_theme(self) -> None:
        """Toggle between light and dark themes."""
        self.is_dark = not self.is_dark
        apply_theme(self.root, self.is_dark)
    
    def build_search_tab(self) -> None:
        """Build the search tab UI."""
        # Search Bar
        search_frame = ttk.Frame(self.search_tab)
        search_frame.pack(fill='x', padx=10, pady=10)
        
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var, font=('Arial', 12))
        entry.pack(side='left', expand=True, fill='x', padx=(0, 5))
        entry.bind('<Return>', lambda e: self.perform_search())
        
        ttk.Button(search_frame, text="Search", command=self.perform_search).pack(side='right')
        
        # Results area
        self.results_text = tk.Text(self.search_tab, wrap='word', state='disabled', font=('Arial', 10))
        self.results_text.pack(expand=True, fill='both', padx=10, pady=(0, 10))
    
    def build_library_tab(self) -> None:
        """Build the library tab UI."""
        btn_frame = ttk.Frame(self.library_tab)
        btn_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Add PDF/EPUB to Library", command=self.add_files).pack(side='left')
        
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side='right')
    
    def add_files(self) -> None:
        """Open file dialog to add files to the library."""
        file_paths = filedialog.askopenfilenames(
            title="Select Files",
            filetypes=[("PDF/EPUB Files", "*.pdf *.epub"), ("All Files", "*.*")]
        )
        if not file_paths:
            return
        
        self.status_var.set(f"Indexing {len(file_paths)} files...")
        
        # Threaded indexing
        def process() -> None:
            success = 0
            errors = []
            
            for path in file_paths:
                try:
                    index_file(path)
                    success += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(path)}: {str(e)}")
            
            # Update UI on main thread
            self.root.after(0, lambda: self._indexing_complete(success, len(file_paths), errors))
        
        threading.Thread(target=process, daemon=True).start()
    
    def _indexing_complete(self, success: int, total: int, errors: list) -> None:
        """
        Handle indexing completion on the main thread.
        
        Args:
            success: Number of successfully indexed files.
            total: Total number of files.
            errors: List of error messages.
        """
        if errors:
            error_msg = f"Successfully indexed {success}/{total} files.\n\nErrors:\n" + "\n".join(errors)
            self.status_var.set(f"Indexed {success}/{total} files with errors")
            show_error("Indexing Complete with Errors", error_msg)
        else:
            self.status_var.set(f"Indexed {success}/{total} files successfully.")
            show_info("Indexing Complete", f"Successfully indexed {success} files.")
    
    def perform_search(self) -> None:
        """Perform a search based on the current query."""
        query = self.search_var.get().strip()
        if not query:
            return
        
        if self.results_text is None:
            return
        
        self.results_text.config(state='normal')
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, "Searching...\n")
        self.results_text.config(state='disabled')
        
        def do_search() -> None:
            try:
                results = execute_search(query)
            except Exception as e:
                results = []
                print(f"Search error: {e}")
            
            # Update UI on main thread
            self.root.after(0, lambda: self.display_results(results))
        
        threading.Thread(target=do_search, daemon=True).start()
    
    def display_results(self, results: list) -> None:
        """
        Display search results in the results text widget.
        
        Args:
            results: List of search result dictionaries.
        """
        if self.results_text is None:
            return
        
        self.results_text.config(state='normal')
        self.results_text.delete(1.0, tk.END)
        
        if not results:
            self.results_text.insert(tk.END, "No results found.\n")
        else:
            for r in results:
                self.results_text.insert(tk.END, f"Title: {r['title']}\n", "title")
                self.results_text.insert(tk.END, f"Score: {r['score']:.2f}\n", "score")
                self.results_text.insert(tk.END, f"{r['snippet']}\n\n", "snippet")
        
        self.results_text.tag_config("title", font=('Arial', 12, 'bold'))
        self.results_text.tag_config("score", foreground="gray")
        self.results_text.config(state='disabled')
