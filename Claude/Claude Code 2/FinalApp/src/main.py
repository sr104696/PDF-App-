"""Entry point for PDF Intelligence desktop app.

Usage:
  python -m src.main          # launch GUI
  python -m src.main index <file_or_folder>...   # CLI index
  python -m src.main search "<query>"            # CLI search
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def _gui():
    # Import only tkinter here — everything else is deferred inside App.__init__
    from src.ui.app_ui import App
    app = App()
    app.mainloop()


def _cli_index(paths):
    from src.index.schema import get_connection
    from src.index.indexer import index_paths

    conn = get_connection()

    def cb(path, cur, total):
        print(f"  [{cur}/{total}] {path}")

    import os
    from pathlib import Path
    from src.utils.constants import SUPPORTED_EXTS
    all_paths = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    if Path(f).suffix.lower() in SUPPORTED_EXTS:
                        all_paths.append(os.path.join(root, f))
        else:
            all_paths.append(p)

    print(f"Indexing {len(all_paths)} file(s)…")
    counts = index_paths(all_paths, conn, progress_cb=cb)
    print(f"Done — {counts}")


def _cli_search(query):
    from src.index.schema import get_connection
    from src.search.searcher import search

    conn = get_connection()
    resp = search(conn, query)
    print(f"\nQuery:   {resp.query}")
    print(f"Intents: {', '.join(resp.intents)}")
    print(f"Results: {len(resp.results)}  ({resp.elapsed_ms:.0f} ms)\n")
    for i, r in enumerate(resp.results, 1):
        print(f"[{i}] {r.title}  p.{r.page_num}  score={r.score}  [{r.structure_type}]")
        print(f"    {r.snippet[:200]}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        _gui()
    elif args[0] == "index":
        _cli_index(args[1:])
    elif args[0] == "search" and len(args) >= 2:
        _cli_search(" ".join(args[1:]))
    else:
        print(__doc__)
        sys.exit(1)
