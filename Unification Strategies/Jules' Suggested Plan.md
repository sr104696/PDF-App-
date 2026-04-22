# Jules' Suggested Plan: A Unified PDF Intelligence Platform

## Overview
The goal of this architectural plan is to synthesize the various independent implementations of the PDF Searcher application into a single, cohesive, and highly optimized core. Currently, the repository contains fragmented approaches:
- **Offline Desktop Implementations (Python/Tkinter):** Found in `Implementation 1`, `Kimi`, `Qwen Coder`, `Lovable`. These prioritize an offline-first experience, leveraging SQLite (FTS5 + BM25), `pdfplumber` for native PDF extraction, Tesseract for OCR, and lightweight PyInstaller deployment.
- **Modern Web/React Implementations:** Found in `Base44` and other React-based snippets (from the Lovable architecture doc). These offer a modern UI (Tailwind, Lucide icons), client-side extraction using PDF.js, and a polished search experience.

This plan proposes weaving these strengths together into a unified **Local-First Web Architecture** using a Python backend (FastAPI) and a React/Tailwind frontend, packaged as a lightweight desktop app (via Electron, Tauri, or PyWebView).

---

## 1. Unified Architecture Paradigm
We will adopt a **Decoupled Client-Server Desktop Model**.
- **Backend (Python):** Handles heavy lifting: OCR, advanced semantic chunking, SQLite FTS indexing, and BM25 search.
- **Frontend (React/Vite):** Delivers a rich, responsive, and visually appealing user interface.
- **Packaging:** Both are bundled together into a single executable using an embedded browser window (e.g., PyWebView) or an Electron/Tauri wrapper, ensuring it remains an offline desktop app.

### Why this approach?
- **Best of Both Worlds:** We get the powerful Python data science/text processing ecosystem (`pdfplumber`, `pytesseract`, `NLTK/SnowballStemmer`) alongside a modern, fluid React UI that Tkinter cannot match.
- **Modularity:** The Python core can be tested and run headlessly. The React frontend can be developed independently.

---

## 2. Core Components Integration Strategy

### 2.1 Text Extraction & Ingestion
*From Python Implementations (Kimi, Lovable, Qwen) + React (Base44)*
- **Primary PDF Extraction:** Use the Python backend with `pdfplumber` for precise layout and text extraction. It handles large files better than client-side `pdf.js` for heavy processing.
- **Fallback / OCR:** Integrate `pytesseract` in the Python backend. If `pdfplumber` detects an image-only PDF, it triggers the OCR pipeline (as seen in the Qwen/Lovable docs).
- **EPUB Support:** Use `ebooklib` + `BeautifulSoup` in the Python backend.
- **UI Integration:** The React frontend handles the drag-and-drop upload zone, streaming files to the Python backend via a local API, and displaying real-time indexing progress via Server-Sent Events (SSE) or WebSockets.

### 2.2 Semantic Chunking
*From Lovable / Qwen Coder*
- Implement the Python layered chunker (`src/core/chunker.py`):
  1. Split by paragraphs.
  2. Split oversized paragraphs by sentences (NLTK punkt fallback to regex).
  3. Enforce `MAX_CHUNK_TOKENS = 512` and `CHUNK_OVERLAP_TOKENS = 32`.
- Store chunks with stable SHA1 IDs for incremental indexing.

### 2.3 Storage and Indexing
*From Lovable / Implementation 1*
- **SQLite + WAL Mode:** Ensure the database uses `WAL` and `synchronous=NORMAL` for concurrent read/write during indexing.
- **Incremental Indexing:** Store `(file_size, file_mtime)` fingerprints. Skip re-parsing unchanged files.
- **FTS5 Virtual Tables:** Use SQLite FTS5 for fast prefix/glob candidate generation.

### 2.4 Search Pipeline
*From Lovable / Base44*
- **Two-Phase Retrieval (Backend):**
  1. **Candidate Gen:** SQLite FTS5 matches (capped at ~200).
  2. **Rerank:** Pure-Python Okapi BM25 scoring over term frequencies.
- **Query Parsing:** Implement stop-word removal, English stemming (Snowball), and domain-specific synonym expansion.
- **Faceted Search (Frontend + Backend):** The backend aggregates facet counts (Author, Year, Type), and the React frontend renders the interactive `FacetSidebar`.
- **Typo Fallback:** Use `rapidfuzz` if FTS5 returns 0 hits.

### 2.5 User Interface (React + Tailwind)
*From Base44 / Lovable Docs*
- **Theme:** Adopt the dark/light mode Tailwind configuration from the React reference.
- **Pages:**
  - **Library (`/`):** Grid/List view of documents, sync status, and the UploadZone.
  - **Search (`/search`):** Search input with BM25 tags, highlighting search terms in results (`<mark>`), and sidebar facets.
  - **Tools (`/tools`):** Index statistics, manual OCR triggers, and index management (Clear all).
- **State Management:** Use `@tanstack/react-query` to manage API calls to the local Python backend, ensuring UI remains responsive.

---

## 3. Directory Structure Consolidation

```text
/unified_pdf_intelligence/
├── backend/
│   ├── app.py                 # FastAPI server entry point
│   ├── api/                   # REST endpoints / WebSockets for progress
│   ├── core/                  # Extraction, Chunker, Tokenizer
│   ├── index/                 # SQLite Schema, Indexer
│   ├── search/                # BM25, FTS Query Gen, Facets
│   └── utils/                 # File hashing, Synonyms
├── frontend/
│   ├── src/
│   │   ├── components/        # React components (UploadZone, DocumentCard, etc.)
│   │   ├── pages/             # Library, Search, Tools
│   │   ├── lib/               # Query hooks, Tailwind utils
│   │   └── App.jsx            # React Router setup
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.js
├── database/                  # Local SQLite DB storage (ignored in git)
├── requirements.txt           # Python dependencies
├── build_scripts/             # PyInstaller / PyWebView build scripts
└── README.md
```

---

## 4. Execution Roadmap

**Phase 1: Backend Foundation**
- Extract the best-performing `indexer.py`, `searcher.py`, and `chunker.py` from the `Qwen Coder` (optimized) and `Lovable` branches.
- Wrap these core functions in a lightweight `FastAPI` application.
- Ensure SQLite connection pooling is thread-safe for UI polling.

**Phase 2: Frontend Implementation**
- Initialize a Vite + React project.
- Port the React components from the `Base44` architecture doc (Layout, UploadZone, DocumentCard, SearchResult).
- Replace the mocked `base44Client` calls with `fetch` or `axios` calls to the local FastAPI server.

**Phase 3: Integration & IPC**
- Wire the React frontend to the FastAPI backend.
- Implement Server-Sent Events (SSE) for real-time progress updates during the `IndexingModal` phase.

**Phase 4: Packaging & Distribution**
- Use `PyWebView` to launch a native OS window displaying the React frontend served by the FastAPI backend.
- Configure `PyInstaller` to bundle the Python environment, the compiled React assets (`frontend/dist`), and the SQLite schema into a single executable.
- Optimize bundle size (exclude unnecessary heavy ML libs like torch/numpy, rely on Tesseract CLI).

---

## 5. Conclusion
By decoupling the heavy data-processing pipeline (Python) from the user interface (React), we create an application that is both powerful and beautiful. This hybrid approach uses every aspect of the codebase—the deep optimization of the Qwen backend, the architectural purity of Lovable, and the slick UI components of Base44—resulting in a truly integrated, best-in-class local PDF search application.