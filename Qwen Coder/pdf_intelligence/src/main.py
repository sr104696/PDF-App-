"""
PDF Intelligence Offline - Main Entry Point
Optimized version with improved error handling and logging.
"""
import os
import sys
import logging

# Ensure src is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from src.ui.app_ui import AppUI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_intelligence.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the application."""
    try:
        root = tk.Tk()
        app = AppUI(root)
        logger.info("Application started successfully")
        root.mainloop()
    except Exception as e:
        logger.error(f"Application failed to start: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
