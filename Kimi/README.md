# PDF Intelligence (Offline Search)

A lightweight, offline-first desktop application for indexing PDF and EPUB libraries and searching them with intelligent BM25 ranking. No internet, no LLMs, no cloud.

## Features
- **Offline Semantic Search** – BM25 + Snowball stemming + optional synonym boost.
- **Semantic Chunking** – Structure-aware splitting (paragraph → sentence → token cap).
- **OCR** – Optional Tesseract integration for scanned PDFs.
- **EPUB Support** – Direct text extraction and indexing.
- **Faceted Filtering** – Filter by author, year, file type, tags with live counts.
- **Dark/Light Mode** – One-click theme toggle.
- **Keyboard Shortcuts** – `Ctrl+F` search, `Ctrl+O` add files, `Esc` clear.

## Quick Start

1. Install Python 3.10+ and [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (optional, for OCR only).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch:
   ```bash
   python main.py
   ```
   Or on Windows, double-click `launch.bat`.

## Usage
- **Library** – Drag & drop PDF/EPUB files or click Browse to index.
- **Search** – Type natural queries. Results are reranked by BM25. Use the sidebar to drill down by author, year, or type.
- **Tools** – Run OCR on scanned PDFs or extract EPUB text.

## Packaging (PyInstaller)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --upx-dir=UPX main.py
```

## Architecture Notes
- **Tier 0–2 Offline** – FTS5 candidate generation → BM25 reranking. No network required.
- **Tier 3 Facets** – SQLite aggregation queries against result sets.
- **Tier 5 Online** – HyDE/embedding mode is reserved for future opt-in configuration.
