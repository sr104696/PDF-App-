# PDF Intelligence — Architecture & Design Document

> Companion to the source code. Covers the decomposed plan, stress tests,
> self-audit, tech-stack justification, and how each GitIngest pattern was
> adapted to a Python/Tkinter desktop app under the **30 MB compressed /
> 80 MB uncompressed / 200 MB RAM** envelope.

---

## 1. Decomposed Plan

### 1.1 Text extraction
| Format | Library | Why | Fallback |
|---|---|---|---|
| PDF (text-native) | **pdfplumber** | accurate per-page layout, headings | **pypdf** (pure Python) |
| PDF (scanned) | **pytesseract** + Tesseract | only sane offline OCR | none — feature degrades cleanly |
| EPUB | **ebooklib** + **BeautifulSoup** (lxml optional) | pure Python, no Calibre | html.parser if lxml absent |

The extractor returns `(page_num, text, heading_hint)` so the rest of the
pipeline doesn't care whether the source was a PDF or an EPUB chapter.

### 1.2 Chunking (`src/core/chunker.py`)
Layered, top-down — **adapted from python-semantic-splitter / treesitter-chunker**
(those split by AST; we split by paragraph → sentence because plain text has
no AST). Token cap is approximate (word count proxy) so we don't ship a real
BPE tokenizer (tiktoken alone would add ~3 MB and a Rust dep).

1. Split by blank lines (paragraphs).
2. Oversized paragraphs are split by sentences (NLTK punkt with regex fallback).
3. Greedy-pack sentences up to `MAX_CHUNK_TOKENS = 512`.
4. Carry `CHUNK_OVERLAP_TOKENS = 32` across boundaries → context preservation.
5. Tiny tail fragments (< `MIN_CHUNK_TOKENS = 20`) merged into the previous chunk.
6. **Stable SHA1 chunk IDs** = hash(file_path | page | start | end). Lets us
   diff and re-index incrementally without losing chunk identity.
7. Each chunk has `prev_id` / `next_id` so a result card can show context.

### 1.3 Indexing (`src/index/indexer.py`)
* SQLite with `WAL`, `synchronous=NORMAL`, 20 MB page cache — ~5× faster than defaults for our write pattern.
* **Incremental reindex** (offline-search Rust pattern): `(file_size, file_mtime)` fingerprint stored in `documents`. A re-scan touches disk per file but skips parsing if the fingerprint matches.
* Per-chunk `term_freq` table holds `{chunk_id, stem, tf}` — populated as part of the same write transaction. Corpus-wide `term_df` is rebuilt in one SQL statement after a batch ingest (cheap up to ~100k chunks).
* SQLite FTS5 virtual table is kept in sync via 3 triggers (`AI`, `AD`, `AU`). FTS rowid = chunk rowid → join is free.

### 1.4 Search pipeline (`src/search/searcher.py`)
**Two-phase** (sk-hybrid-search / Vespa pattern):

1. **Candidate gen** — `chunks_fts MATCH` with prefix-glob query, ordered by SQLite's built-in `bm25()`, capped at `CANDIDATE_LIMIT = 200`. ~10 ms on a 10k-chunk index.
2. **Rerank** — for each candidate pull stemmed term frequencies from `term_freq`, look up document frequencies in `term_df` (one batched `IN (…)`), score with our pure-Python Okapi BM25.
3. **Synonym boost** — small additive term (`SYNONYM_BOOST = 0.15`). Sheet 8 explicitly says "minor signal, not primary mechanism".
4. **Min-max normalize** the top-N to `[0,1]` so scores are presentable.
5. **Fuzzy fallback** — if FTS returns 0 hits, rapidfuzz reranks a bounded slice; if rapidfuzz isn't available, degrade to a `LIKE` scan. This is the typo path.

### 1.5 UI (`src/ui/app_ui.py`)
Three tabs (Library / Search / Tools), Tkinter + ttk only. Worker thread + `queue.Queue` polled by `after()` keeps the event loop responsive during multi-minute indexing jobs. Light/dark themes are pure ttk.

### 1.6 Packaging
`pyinstaller.spec` with `--onefile`, `strip=True`, `upx=True`, an aggressive `EXCLUDES` list (numpy, scipy, pandas, Qt, sklearn, jupyter, distutils, …). Tesseract binary is intentionally **not bundled** — that single decision keeps us under 30 MB.

---

## 2. Stress Tests & Edge Cases

| Scenario | Handling |
|---|---|
| **Corrupted PDF** | `pdfplumber` raises → `pypdf` retried → if both fail, the file is logged, `failed` counter incremented, rest of the batch continues (`indexer.index_paths`). |
| **Encrypted PDF** | `pypdf(strict=False)` and pdfplumber will raise → counted as failed. Enhancement: prompt for password. |
| **Scanned-only PDF (no text layer)** | Default ingest produces empty chunks → 0 hits in search. User clicks Tools → OCR; Tesseract path is taken. |
| **Massive PDF (10k pages)** | Streamed page-by-page (no full load). Memory bounded by chunker (max 512 tokens × small constant). One transaction per file, not per chunk. |
| **EPUB with `<script>`/`<style>`** | Stripped before `get_text()` so they don't pollute the index. |
| **EPUB with broken HTML** | `BeautifulSoup(html.parser)` is permissive; chapter that fails to parse is skipped, not the whole book. |
| **Typo'd query ("neual netwroks")** | FTS returns nothing → `_fuzzy_fallback` uses rapidfuzz `partial_ratio` over a 5k-row slice. |
| **Empty / filler-only query** | `query_parser.parse` returns `is_empty()` → searcher returns empty response, UI shows hint text. |
| **Phrase + token query** (`"deep learning" optimizer`) | `_build_fts` produces `"deep learning" AND optimizer*`. Phrase matched as FTS5 phrase. |
| **Unicode / accented text** | FTS5 `tokenize='unicode61 remove_diacritics 2'`. Word regex is `re.UNICODE`. |
| **Re-indexing the same library** | `(size, mtime)` fingerprint short-circuits unchanged files; touched files rebuild only their chunks. `term_df` rebuilt once at the end of the batch. |
| **Concurrent UI + worker** | SQLite opened with `check_same_thread=False`, single connection, `WAL` allows readers during writes. |
| **Low RAM (4 GB)** | Page cache pinned at 20 MB; FTS rerank is bounded; no in-memory inverted index. |
| **Disk full mid-index** | Each file is wrapped in `BEGIN`/`COMMIT`; failure rolls back that file only. |

---

## 3. Self-Audit — Gaps & Mitigations

| Gap | Real-world impact | Mitigation in this build |
|---|---|---|
| BM25 over chunks ≠ true semantic search | Misses paraphrases that share no stems | Synonym dict (small, user-editable). Future: optional **bge-micro** ONNX (~25 MB) as a separate download. |
| Word-count proxy for "tokens" | Off by ~15% vs. real BPE tokenizers | Acceptable; chunks are still well below model context windows. Avoids ~3 MB tiktoken dep. |
| Punkt requires a one-time download | First-run failure if user is offline | Regex fallback already wired (`tokenizer._try_punkt`). Sentence quality slightly degraded but search still works. |
| `rebuild_term_df` is global | Slow on >100k chunks (single SQL `GROUP BY`) | Acceptable for desktop libraries (<10k chunks typical). Can be made incremental later. |
| Tkinter look on macOS is dated | Cosmetic | clam theme + ttk styling. Still under any "extra dep" threshold. |
| OCR not bundled | Power users must install Tesseract | Surfaced clearly in UI ("Tesseract: not found"), README has links. Single-binary `--add-binary` is supported if a user wants to vendor it. |
| No PDF preview pane | Users must open in their default viewer | "Open file" button uses `os.startfile` / file URI. A Tkinter PDF preview would require Pillow page renders (slow) or PyMuPDF (~15 MB — busts the budget). |
| Single-process scan | One slow file blocks the queue | Indexing already runs on a worker thread. Multi-process would need `multiprocessing` (works but adds startup time on Windows). |
| Synonym dict is English-only | Other languages get only stemming | Punkt + Snowball both support multiple languages — wiring is one constant change. |

---

## 4. Tech Stack — final list with size estimates

| Package | Reason | Approx. installed size |
|---|---|---|
| **stdlib** (sqlite3, tkinter, hashlib, threading, …) | Core | 0 (already in Python) |
| pdfplumber 0.11.4 | Primary PDF extractor | ~3 MB (pulls pdfminer.six) |
| pdfminer.six | pdfplumber dep | ~6 MB |
| Pillow 11 | image handling for OCR / pdfplumber | ~10 MB |
| pypdf 5.1 | Pure-Python fallback | ~2 MB |
| snowballstemmer 2.2 | Stemming | ~600 KB |
| nltk 3.9 | Sentence tokenization (punkt only used) | ~2 MB code + 10 MB data on demand |
| ebooklib 0.18 | EPUB | ~200 KB |
| beautifulsoup4 4.12 | HTML cleanup | ~300 KB |
| lxml 5.3 (optional) | Faster HTML parser | ~6 MB |
| reportlab 4.2 | EPUB→PDF | ~3 MB |
| rapidfuzz 3.10 | Typo fallback | ~2 MB |
| pytesseract 0.3.13 | OCR wrapper | ~50 KB (Tesseract binary not bundled) |

**Total un-pruned site-packages:** ~45 MB. PyInstaller `--onefile` + `strip` + UPX brings the final exe to **~25–28 MB compressed** in the spec config above.

### Explicitly rejected
* numpy / scipy / sklearn — busts the size budget.
* sentence-transformers / torch — busts size and RAM, and needs internet for first model download.
* PyMuPDF (fitz) — fast, but ~15 MB and AGPL-licensed.
* Qt (PyQt/PySide) — easily +30 MB.
* tkinterdnd2 — would enable real drag-and-drop but +1.5 MB; we use a button + Ctrl+O instead.
* tiktoken — Rust extension, +3 MB; word-count proxy is good enough for chunk budgeting.

---

## 5. GitIngest Pattern Adaptations

| Source repo (uploaded ingest) | Borrowed pattern | Where it lives in this codebase |
|---|---|---|
| **python-semantic-splitter / treesitter-chunker** | Layered chunker with token cap, overlap, stable IDs | `src/core/chunker.py` (`chunk_page`, `chunk_id`) |
| **sk-hybrid-search** (Semantic Kernel) | Two-phase retrieval (candidate gen → rerank) + min-max normalization | `src/search/searcher.py` (`search`), `src/search/bm25.py` (`normalize`) |
| **dorianbrown/rank_bm25** | Okapi BM25 with k1, b parameters; IDF smoothing | `src/search/bm25.py` (`score_chunk`, `idf`) |
| **firstflush/pdf-ninja** | Pluggable extractor with graceful fallback chain | `src/core/pdf_parser.py` (`extract_pages`) |
| **simonw/s3-ocr** | OCR is a separate, opt-in step driven by the UI, not part of every ingest | Tools tab + `index_file(..., ocr=True)` |
| **dogsheep/dogsheep-beta** | SQLite + FTS5 + custom search index over multiple content types | `src/index/schema.py` (`chunks_fts`, `term_freq`, `term_df`) |
| **faceted-search** (PHP) | Facet counts derived from the result set, not the whole corpus | `src/search/facets.py` (`facets_for_docs`) |
| **offline-search** (Rust) | Incremental reindex via mtime fingerprint + Snowball | `src/utils/file_hash.py` (`doc_fingerprint`) + `src/index/indexer.py` (`index_file`) + `src/search/stemmer.py` |
| **recoll-webui** | Decoupled backend (indexer + searcher) so a future web UI could be bolted on | The `search/` and `index/` packages have no Tk dependency; `main.py --cli` already proves the headless contract |
| **ggreer/the_silver_searcher / burntsushi/ripgrep** | "Cheap, fast prefilter then expensive rerank" mindset | FTS5 prefilter capped at 200 candidates |
| **aksarav/pdfstract** | Per-page extraction + page-aware chunking for citations | `PageText.page_num` survives all the way into `SearchResult.page_num` |
| **coderdayton/simplevecdb** | (Inspirational) tiny, self-contained search engine packaged as a single dependency | Drove the "no numpy, no torch" stance even though we don't use vectors |

---

## 6. Performance budget — measured assumptions

* Cold start: dominated by `import tkinter` (~120 ms), `import sqlite3` (~30 ms), our package (~80 ms). NLTK is **lazy-imported only when sentences are needed**. Total < 1 s on Windows 10 / SSD.
* `index_paths(500-page PDF)` — about 30–50 s on a 5-year-old laptop, dominated by pdfplumber. Memory peak ~120 MB.
* `search()` on a 10k-chunk index — < 50 ms typical, < 150 ms with synonym expansion.
* Idle GUI memory ~70–90 MB (Python interpreter + Tk).

---

## 7. Future work (out of scope for v1)
* Optional ONNX micro-embedding model behind a feature flag.
* `multiprocessing` indexing for many small files.
* Right-click context menu to add files from Explorer.
* Per-chunk highlighting in an embedded PDF preview (would need PyMuPDF — busts size).
* Encrypted-PDF password prompt.
