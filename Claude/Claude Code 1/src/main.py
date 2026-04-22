"""
main.py — Application entry point.

Modes:
  GUI  (default)      python -m src.main
  CLI index           python -m src.main index ./books/
  CLI search          python -m src.main search "BM25 ranking"
  CLI search (JSON)   python -m src.main search "BM25 ranking" --json

The CLI mode is headless (no Tkinter), which proves the backend
is cleanly decoupled from the UI layer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure the project root is on sys.path when running as a script
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _cli_index(args: argparse.Namespace) -> None:
    from src.index.indexer import ensure_db, index_paths
    from src.utils.constants import SUPPORTED_EXTENSIONS

    ensure_db()
    paths: list[str] = []
    for target in args.paths:
        if os.path.isfile(target):
            paths.append(target)
        elif os.path.isdir(target):
            for root_dir, _dirs, files in os.walk(target):
                for fn in files:
                    if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTENSIONS:
                        paths.append(os.path.join(root_dir, fn))
        else:
            print(f"Warning: '{target}' not found, skipped.", file=sys.stderr)

    if not paths:
        print("No supported files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Indexing {len(paths)} file(s)…")

    def _cb(fp, fi, ft, pg, pgt):
        fn = os.path.basename(fp)
        print(f"  [{fi}/{ft}] {fn}  (page {pg}/{max(pgt,1)})", end="\r")

    result = index_paths(paths, progress_cb=_cb)
    print()
    print(
        f"Done: {result['indexed']} indexed, "
        f"{result['skipped']} skipped, "
        f"{result['failed']} failed."
    )
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _cli_search(args: argparse.Namespace) -> None:
    from src.search.searcher import search
    from src.index.indexer import ensure_db

    ensure_db()
    query = " ".join(args.query)
    response = search(query, save_history=False)

    if args.json:
        import dataclasses
        output = [dataclasses.asdict(r) for r in response.results]
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    if not response.results:
        print("No results found.")
        return

    for i, r in enumerate(response.results, start=1):
        print(f"\n{'─'*60}")
        print(f"[{i}] {r.title}  (p. {r.page_num})  score={r.score:.2f}")
        if r.section_header:
            print(f"    § {r.section_header}")
        if r.author or r.year:
            print(f"    {r.author or ''}  {r.year or ''}")
        print(f"    {r.file_path}")
        print(f"\n    {r.snippet}")


def _gui() -> None:
    import tkinter as tk
    from src.ui.app_ui import AppUI
    from src.index.indexer import ensure_db

    ensure_db()
    root = tk.Tk()
    # Set a reasonable icon (skip if no icon file exists)
    _icon = os.path.join(_ROOT, "assets", "icon.png")
    if os.path.exists(_icon):
        try:
            img = tk.PhotoImage(file=_icon)
            root.iconphoto(True, img)
        except Exception:
            pass
    AppUI(root)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdf_intelligence",
        description="Offline PDF & EPUB intelligent search.",
    )
    sub = parser.add_subparsers(dest="command")

    # index sub-command
    p_index = sub.add_parser("index", help="Index PDF/EPUB files or folders.")
    p_index.add_argument("paths", nargs="+", metavar="PATH",
                         help="Files or directories to index.")
    p_index.add_argument("--force", action="store_true",
                         help="Re-index even if file is unchanged.")

    # search sub-command
    p_search = sub.add_parser("search", help="Search the indexed library.")
    p_search.add_argument("query", nargs="+", metavar="WORD",
                          help="Search query words.")
    p_search.add_argument("--json", action="store_true",
                          help="Output results as JSON.")
    p_search.add_argument("--top", type=int, default=20, metavar="N",
                          help="Number of results (default: 20).")

    args = parser.parse_args()

    if args.command == "index":
        _cli_index(args)
    elif args.command == "search":
        _cli_search(args)
    else:
        _gui()


if __name__ == "__main__":
    main()
