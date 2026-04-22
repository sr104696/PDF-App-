# PDF Intelligence

**Offline PDF & EPUB intelligent search.** No cloud. No LLM APIs. No telemetry.
Pure-Python BM25 over a SQLite + FTS5 index, wrapped in a minimal Tkinter UI.

> Built to the v2 spec (sheets 14–21): Snowball stemming, layered semantic
> chunking, two-phase BM25 retrieval, optional synonym boost, faceted filters,
> incremental reindex.

---

## Features

| Area | What it does |
|------|--------------|
| **Indexing** | Drop in PDFs / EPUBs (or a folder). Layered chunker (paragraph → sentence → 512-token window with overlap). Stable SHA1 chunk IDs. Incremental: untouched files are skipped via `(size, mtime)` fingerprint. |
| **Search** | Two-phase: SQLite **FTS5** generates ≤200 candidates → pure-Python **BM25** reranks. Optional synonym additive boost. Min-max score normalization. **rapidfuzz** fallback for typos. |
| **Linguistics** | **Snowball English** stemmer (replaces the brittle suffix-stripping in v1). Punkt sentence tokenizer with regex fallback if NLTK data isn't available offline. |
| **EPUB** | Pure-Python via **ebooklib** + BeautifulSoup. Optional EPUB → PDF via **reportlab** (no wkhtmltopdf, no pandoc). |
| **OCR** | **Optional** — uses the user's installed Tesseract binary (not bundled). The app stays small; OCR is opt-in via the Tools tab. |
| **UI** | Tkinter / ttk. Three tabs: Library / Search / Tools. Light + dark themes. Threaded indexing with progress bar. Search history. Faceted sidebar. |
| **CLI** | `python -m src.main index ./books/`, `python -m src.main search "neural networks"`. |

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.main                   # GUI
python -m src.main index ./books     # CLI: index a folder
python -m src.main search "BM25 ranking"
```

Or just run `launch.bat` (Windows) / `launch.sh` (Linux/macOS).

## Building a single .exe

```bash
pip install pyinstaller
pyinstaller pyinstaller.spec
# → dist/PDFIntelligence.exe
```

Targets: **<30 MB compressed, <80 MB uncompressed**. The spec excludes numpy,
scipy, pandas, Qt, etc., and turns on `strip` + `upx`. Install **UPX** and put
it on PATH for maximum compression.

## OCR (optional)

The Tesseract OCR engine is **not bundled** (it would blow the 30 MB budget).
Install it separately and the **Tools → OCR** button becomes active:

* **Windows**: <https://github.com/UB-Mannheim/tesseract/wiki>
* **macOS**: `brew install tesseract`
* **Debian/Ubuntu**: `sudo apt install tesseract-ocr`

## Architecture

```
src/
├── main.py              # entry point (GUI + CLI)
├── ui/
│   ├── app_ui.py        # Tkinter app (Library / Search / Tools)
│   ├── styles.py        # ttk light/dark themes
│   └── dialogs.py
├── core/
│   ├── pdf_parser.py    # pdfplumber → pypdf → optional OCR
│   ├── epub_parser.py   # ebooklib + BS4
│   ├── chunker.py       # layered semantic chunking
│   └── tokenizer.py     # word + sentence tokenization
├── index/
│   ├── schema.py        # SQLite DDL (documents, chunks, term_freq, term_df, FTS5)
│   ├── migrations.py    # WAL + pragmas + version table
│   └── indexer.py       # ingest, incremental reindex, BM25 stat builder
├── search/
│   ├── query_parser.py  # filler removal, intent detection, FTS expression
│   ├── stemmer.py       # Snowball wrapper
│   ├── bm25.py          # pure-Python Okapi BM25 + min-max normalization
│   ├── facets.py        # SQL-driven facet aggregation
│   └── searcher.py      # two-phase: FTS candidates → BM25 rerank
└── utils/
    ├── constants.py
    ├── file_hash.py     # stable chunk IDs + (size, mtime) fingerprint
    └── synonyms.py      # static dict, additive boost only
data/                    # library.db, synonyms.json, nltk_data/
assets/                  # icon
tests/                   # smoke tests
```

## Performance budget

| Metric | Target | Notes |
|---|---|---|
| Cold start | < 2 s | Tkinter only; lazy NLTK import; no numpy/scipy |
| Index 500-page PDF | < 60 s | pdfplumber bound; OCR adds minutes |
| Search latency | < 100 ms (10k chunks) | FTS5 candidate gen ~10 ms, BM25 rerank ~20 ms |
| Memory (idle) | < 80 MB | grows ~+50 MB during indexing |
| Memory (search) | < 200 MB | bounded by `CANDIDATE_LIMIT = 200` |
| .exe size (UPX) | < 30 MB | enforced by `pyinstaller.spec` excludes |

## Running tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
