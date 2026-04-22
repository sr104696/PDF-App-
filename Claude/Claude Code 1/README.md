# PDF Intelligence v2

**Offline PDF & EPUB intelligent search.** No cloud. No LLM APIs. No telemetry.

Pure-Python Okapi BM25 over a SQLite + FTS5 index, wrapped in a minimal Tkinter UI.

> Built to the v2 spec (sheets 14–21 of PDF Searcher.xlsx):
> Snowball stemming · Layered semantic chunking · Two-phase BM25 retrieval ·
> Optional synonym boost · Faceted filtering · Incremental reindex.

---

## Quick Start

```bash
# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the GUI
python -m src.main

# Or use the launch script:
launch.bat       # Windows
./launch.sh      # Linux / macOS
```

### CLI mode

```bash
# Index a folder of PDFs
python -m src.main index ./books/

# Search (prints results to terminal)
python -m src.main search "BM25 ranking algorithm"

# Search with JSON output (for scripting)
python -m src.main search "neural networks" --json
```

---

## Features

| Area | What it does |
|---|---|
| **Indexing** | Drop in PDFs / EPUBs or whole folders. Layered chunker (paragraph → sentence → 512-token window with 32-token overlap). Stable SHA1 chunk IDs. **Incremental**: untouched files skipped via `(size, mtime)` fingerprint. |
| **Search** | Two-phase: SQLite **FTS5** generates ≤200 candidates → pure-Python **Okapi BM25** reranks. Optional synonym additive boost. Min-max score normalisation to [0,1]. |
| **Linguistics** | **Snowball English** stemmer (replaces brittle v1 suffix-stripping). NLTK Punkt sentence tokeniser with regex fallback when NLTK data isn't available offline. |
| **EPUB** | Pure-Python via **ebooklib** + BeautifulSoup. Optional EPUB → PDF via **reportlab** (no wkhtmltopdf, no pandoc). |
| **OCR** | **Optional** — uses the user's installed Tesseract binary (not bundled). The app stays small; OCR is opt-in via the Tools tab. |
| **UI** | Tkinter / ttk. Three tabs: Library / Search / Tools. **Light + dark** themes. Threaded indexing with progress bar. **Search history** dropdown. **Faceted sidebar** (author, year, file type). |
| **Shortcuts** | `Ctrl+F` focus search · `Ctrl+O` add files · `Ctrl+D` toggle dark mode · `Esc` clear search |
| **CLI** | `python -m src.main index ./books/` · `python -m src.main search "query"` |

---

## Project Structure

```
pdf_intelligence_v2/
├── src/
│   ├── main.py              # entry point (GUI + CLI)
│   ├── core/
│   │   ├── pdf_parser.py    # pdfplumber → pypdf → optional OCR
│   │   ├── epub_parser.py   # ebooklib + BeautifulSoup
│   │   ├── chunker.py       # layered semantic chunker (v2 sheet 14)
│   │   └── tokenizer.py     # word + sentence tokenisation
│   ├── index/
│   │   ├── schema.py        # SQLite DDL, FTS5, triggers
│   │   └── indexer.py       # ingest, incremental reindex, BM25 stat builder
│   ├── search/
│   │   ├── query_parser.py  # filler removal, intent detection, FTS expression
│   │   ├── stemmer.py       # Snowball wrapper
│   │   ├── bm25.py          # pure-Python Okapi BM25 + min-max normalisation
│   │   ├── facets.py        # SQL-driven facet aggregation
│   │   └── searcher.py      # two-phase: FTS5 candidates → BM25 rerank
│   └── utils/
│       ├── constants.py     # all tunable parameters
│       ├── file_hash.py     # stable chunk IDs + (size, mtime) fingerprint
│       └── synonyms.py      # static synonym boost dict (user-editable)
├── data/
│   ├── library.db           # created on first run
│   └── synonyms.json        # user-editable synonym expansions
├── assets/                  # icon.png / icon.ico (optional)
├── tests/
│   └── test_flow.py         # smoke tests (no real PDFs needed)
├── requirements.txt
├── launch.bat               # Windows optimised launcher
├── launch.sh                # Linux / macOS launcher
├── pyinstaller.spec         # build single .exe
├── setup.py
├── README.md
└── ARCHITECTURE.md          # full design doc + stress tests + self-audit
```

---

## OCR (Optional)

The Tesseract OCR engine is **not bundled** (it would add ~40 MB).
Install it separately and the **Tools → Run OCR** button becomes active:

| Platform | Install |
|---|---|
| Windows | https://github.com/UB-Mannheim/tesseract/wiki |
| macOS | `brew install tesseract` |
| Debian/Ubuntu | `sudo apt install tesseract-ocr` |

---

## Building a Single .exe

```bash
pip install pyinstaller
# Install UPX for maximum compression: https://upx.github.io/
pyinstaller pyinstaller.spec
# → dist/PDFIntelligence.exe   (~25-30 MB with UPX)
```

Targets: **<30 MB compressed, <80 MB uncompressed**.

---

## Running Tests

```bash
python -m unittest tests.test_flow -v
```

Tests create a temporary SQLite database with synthetic data — no real PDFs required.

---

## Performance Budget

| Metric | Target | Notes |
|---|---|---|
| Cold start | < 2 s | Tkinter only; lazy NLTK import; no numpy/scipy |
| Index 500-page PDF | < 60 s | pdfplumber bound; OCR adds minutes |
| Search latency | < 100 ms (10k chunks) | FTS5 candidate gen ~10 ms, BM25 rerank ~20 ms |
| Memory (idle) | < 80 MB | grows ~+50 MB during indexing |
| Memory (peak) | < 200 MB | bounded by `CANDIDATE_LIMIT = 200` |
| .exe size (UPX) | < 30 MB | enforced by `pyinstaller.spec` excludes |

---

## Tunable Parameters

All parameters live in `src/utils/constants.py`:

```python
MAX_CHUNK_TOKENS  = 512   # max words per chunk
CHUNK_OVERLAP_TOKENS = 32 # overlap between adjacent chunks
CANDIDATE_LIMIT   = 200   # FTS5 candidate pool before BM25 rerank
BM25_K1 = 1.5             # BM25 term saturation
BM25_B  = 0.75            # BM25 length normalisation
SYNONYM_BOOST = 0.15      # additive score bonus for synonym hits
SEARCH_HISTORY_MAX = 10   # last N queries stored
```

---

## License

MIT
