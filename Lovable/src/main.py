"""Entry point. Handles `--cli` mode for headless indexing/searching."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .index.migrations import open_db
from .index import indexer
from .search import searcher
from .utils.constants import APP_NAME, APP_VERSION, DATA_DIR, DB_PATH

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


def _cli(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="pdf-intel", description=APP_NAME)
    p.add_argument("--version", action="version", version=APP_VERSION)
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("index", help="Index files or folders")
    pi.add_argument("paths", nargs="+")
    pi.add_argument("--ocr", action="store_true")

    ps = sub.add_parser("search", help="Search the library")
    ps.add_argument("query")
    ps.add_argument("--limit", type=int, default=10)

    sub.add_parser("list", help="List indexed documents")

    args = p.parse_args(argv)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = open_db(DB_PATH)

    if args.cmd == "index":
        def cb(msg, done, total):
            print(f"  [{done}/{total}] {msg}")
        stats = indexer.index_paths(conn, [Path(x) for x in args.paths],
                                    ocr=args.ocr, progress=cb)
        print(stats)
        return 0
    if args.cmd == "search":
        resp = searcher.search(conn, args.query, limit=args.limit)
        print(f"{len(resp.results)} result(s) in {resp.elapsed_ms:.1f} ms")
        for i, r in enumerate(resp.results, 1):
            print(f"\n[{i}] {r.title}  p.{r.page_num}  score={r.score:.3f}")
            print(f"    {r.file_path}")
            print(f"    {r.snippet}")
        return 0
    if args.cmd == "list":
        for d in indexer.list_documents(conn):
            print(f"{d['id']:>4}  {d['file_type']:>4}  p={d['page_count']:>4}  {d['title']}")
        return 0

    p.print_help()
    return 2


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"index", "search", "list", "--version"}:
        return _cli(sys.argv[1:])
    # GUI mode (default)
    from .ui.app_ui import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
