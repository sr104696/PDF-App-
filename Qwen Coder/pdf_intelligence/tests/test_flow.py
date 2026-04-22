"""
Test Flow Module - Improved test robustness.
"""
import os
import sys
import tempfile

# Ensure src is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.index.indexer import index_file
from src.search.searcher import execute_search
from src.index.schema import initialize_db


def create_dummy_pdf(path: str) -> None:
    """
    Create a dummy PDF file for testing.
    
    Args:
        path: Path where the PDF will be created.
    """
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path)
    c.drawString(100, 750, "This is a test document about Python programming and offline search.")
    c.drawString(100, 730, "We are testing the BM25 algorithm and sqlite FTS5 integration.")
    c.showPage()
    c.save()


def main() -> None:
    """Run the test flow."""
    print("Initializing DB...")
    initialize_db()
    
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        test_pdf_path = tmp.name
    
    try:
        print(f"Creating dummy PDF at {test_pdf_path}...")
        try:
            import reportlab
            create_dummy_pdf(test_pdf_path)
        except ImportError:
            print("reportlab not installed, skipping PDF creation test.")
            return
        
        print(f"Indexing {test_pdf_path}...")
        try:
            index_file(test_pdf_path)
            print("Indexing successful.")
        except Exception as e:
            print(f"Error during indexing: {e}")
            return
        
        print("\nExecuting Search for 'Python'...")
        results = execute_search("Python")
        if results:
            for r in results:
                print(f"Match: {r['title']} | Score: {r['score']:.2f}")
                print(f"Snippet: {r['snippet'][:100]}...")
        else:
            print("No results found.")
        
        print("\nExecuting Search for 'offline algorithm'...")
        results = execute_search("offline algorithm")
        if results:
            for r in results:
                print(f"Match: {r['title']} | Score: {r['score']:.2f}")
                print(f"Snippet: {r['snippet'][:100]}...")
        else:
            print("No results found.")
    
    finally:
        # Clean up test file
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)
            print(f"\nCleaned up test file: {test_pdf_path}")


if __name__ == "__main__":
    main()
