#!/usr/bin/env python3
"""
PDF Search Application - Integrated and Optimized
Combines the best features from all source materials
"""
import os
import sys
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue

# Ensure we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import core modules
from pdf_parser import extract_text_from_pdf
from chunker import chunk_text
from tokenizer import tokenize
from indexer import index_file
from searcher import execute_search
from schema import initialize_db, get_db_connection
from utils import setup_logging

class PDFSearchApp:
    """Main PDF Search Application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Search Pro")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # Initialize database
        initialize_db()
        
        # Setup logging
        self.logger = setup_logging()
        
        # Application state
        self.search_queue = queue.Queue()
        self.indexing = False
        self.search_results = []
        
        # Create UI
        self.create_widgets()
        self.setup_bindings()
        
        # Start processing thread
        self.start_processing_thread()
    
    def create_widgets(self):
        """Create all UI widgets"""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Search bar
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=('Arial', 14))
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        search_entry.focus()
        
        search_btn = ttk.Button(search_frame, text="Search", command=self.queue_search)
        search_btn.pack(side=tk.RIGHT)
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(action_frame, text="Add PDFs", command=self.add_pdfs).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_frame, text="Clear Index", command=self.clear_index).pack(side=tk.LEFT)
        
        # Results area
        results_frame = ttk.Frame(main_frame)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Results list
        self.results_listbox = tk.Listbox(results_frame, font=('Arial', 12))
        self.results_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_listbox.bind('<<ListboxSelect>>', self.show_result_detail)
        
        # Result detail
        detail_frame = ttk.Frame(results_frame, width=300)
        detail_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        ttk.Label(detail_frame, text="Result Detail", font=('Arial', 12, 'bold')).pack(pady=(0, 10))
        self.detail_text = tk.Text(detail_frame, wrap=tk.WORD, height=20)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN).pack(fill=tk.X, pady=(10, 0))
    
    def setup_bindings(self):
        """Setup key bindings"""
        self.root.bind('<Return>', lambda e: self.queue_search())
        self.root.bind('<Control-o>', lambda e: self.add_pdfs())
        self.root.bind('<Control-l>', lambda e: self.clear_index())
    
    def start_processing_thread(self):
        """Start background processing thread"""
        def processing_loop():
            while True:
                try:
                    task = self.search_queue.get()
                    if task == "EXIT":
                        break
                    elif task == "SEARCH":
                        self.perform_search()
                    elif task == "INDEX":
                        self.perform_indexing()
                except Exception as e:
                    self.logger.error(f"Processing error: {e}")
        
        self.processing_thread = threading.Thread(target=processing_loop, daemon=True)
        self.processing_thread.start()
    
    def queue_search(self):
        """Queue a search operation"""
        query = self.search_var.get().strip()
        if query:
            self.search_queue.put("SEARCH")
            self.status_var.set("Searching...")
    
    def perform_search(self):
        """Perform the actual search"""
        try:
            query = self.search_var.get().strip()
            if not query:
                return
            
            results = execute_search(query, top_k=20)
            self.search_results = results
            
            # Update UI
            self.root.after(0, self.update_search_results)
            self.status_var.set(f"Found {len(results)} results")
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            self.status_var.set(f"Search error: {e}")
    
    def update_search_results(self):
        """Update the results listbox"""
        self.results_listbox.delete(0, tk.END)
        for i, result in enumerate(self.search_results, 1):
            self.results_listbox.insert(tk.END, f"{i}. {result['title']} (Score: {result['score']:.2f})")
    
    def show_result_detail(self, event):
        """Show detailed information about selected result"""
        selection = self.results_listbox.curselection()
        if selection:
            index = selection[0]
            result = self.search_results[index]
            
            detail_text = f"Title: {result['title']}\n"
            detail_text += f"Score: {result['score']:.2f}\n\n"
            detail_text += f"Snippet:\n{result['snippet']}"
            
            self.detail_text.delete(1.0, tk.END)
            self.detail_text.insert(tk.END, detail_text)
    
    def add_pdfs(self):
        """Add PDF files to index"""
        file_paths = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        
        if file_paths:
            self.status_var.set(f"Indexing {len(file_paths)} files...")
            self.search_queue.put("INDEX")
    
    def perform_indexing(self):
        """Perform file indexing"""
        try:
            file_paths = filedialog.askopenfilenames(
                title="Select PDF files",
                filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
            )
            
            if not file_paths:
                return
            
            for file_path in file_paths:
                try:
                    index_file(file_path)
                    self.logger.info(f"Indexed: {file_path}")
                except Exception as e:
                    self.logger.error(f"Failed to index {file_path}: {e}")
            
            self.status_var.set(f"Indexed {len(file_paths)} files")
            
        except Exception as e:
            self.logger.error(f"Indexing failed: {e}")
            self.status_var.set(f"Indexing error: {e}")
    
    def clear_index(self):
        """Clear the search index"""
        if messagebox.askyesno("Clear Index", "Are you sure you want to clear the entire search index?"):
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM documents")
                cursor.execute("DELETE FROM pages_chunks")
                cursor.execute("DELETE FROM term_freq")
                cursor.execute("DELETE FROM term_df")
                conn.commit()
                conn.close()
                
                self.status_var.set("Index cleared")
                self.search_results = []
                self.update_search_results()
                self.detail_text.delete(1.0, tk.END)
                
            except Exception as e:
                self.logger.error(f"Failed to clear index: {e}")
                self.status_var.set(f"Error clearing index: {e}")

def main():
    """Main entry point"""
    try:
        root = tk.Tk()
        app = PDFSearchApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()