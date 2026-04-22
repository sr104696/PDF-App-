# Codex's Suggested Plan

## Objective
Create a **single, production-ready offline PDF/EPUB intelligence app** by consolidating the strongest ideas already present in this repository into one optimized core product, while still keeping extension paths open for future hybrid/online retrieval.

---

## 1) What to Keep From Each Existing Implementation

### Lovable (Primary foundation)
Use Lovable as the base because it already has the most complete end-to-end architecture (core/index/search/ui split, migrations, tests, packaging), including:
- modular package structure in `src/`,
- SQLite + FTS5 + BM25 two-stage retrieval,
- layered chunking + Snowball stemming,
- GUI + CLI parity,
- optional OCR + EPUB support,
- smoke tests and packaging scaffolding.

### Claude / Kimi / Vibestral variants (Selective feature imports)
Treat these variants as **feature donors**, not competing codebases. Pull specific strengths into the unified core:
- CLI/UX enhancements (e.g., richer command options and clearer user flows),
- any query parser ergonomics and shortcut handling that improve user productivity,
- fallback strategies and modular file parsing conveniences,
- architectural documentation patterns (stress tests, explicit constraints, dependency rationale).

### Qwen/Codex optimization notes (Curated backlog input)
Use optimization reports as **hypothesis sources**. Before merging any suggested change:
1. verify in current code,
2. add/adjust tests,
3. benchmark impact,
4. gate behind feature flags if risky.

### External ingested references (`Github Repo GitIngest`)
Use these as a design pattern library for:
- indexing and search performance techniques,
- robust tokenization and filesystem scanning patterns,
- retrieval/ranking tradeoffs.
Do not copy blindly; adapt patterns to the existing schema/contracts.

---

## 2) Unified Target Architecture

### A. Ingestion Layer (PDF/EPUB/OCR)
Build one ingestion contract:
- `Extractor` interface returning normalized page/chapter units: `{unit_id, doc_id, unit_num, heading, text, metadata}`.
- PDF pipeline: `pdfplumber -> pypdf fallback -> optional OCR`.
- EPUB pipeline: `ebooklib + BeautifulSoup` cleaned text extraction.
- OCR stays optional and explicit (tool action + batch mode).

**Unification rule:** all sources become the same normalized unit stream before chunking.

### B. Normalization + Linguistics Layer
Centralize text normalization in one module:
- Unicode normalization,
- punctuation cleanup,
- tokenization,
- stemming (Snowball default),
- optional synonyms expansion loaded from editable JSON.

Add language hooks so future multilingual support only swaps a config profile rather than forking code.

### C. Semantic Chunking Layer
Retain layered chunking as default:
1. page/chapter boundaries,
2. paragraph segmentation,
3. sentence segmentation,
4. token-window packing with overlap.

Add chunk quality telemetry:
- avg chunk length,
- overlap duplication ratio,
- tiny fragment counts,
- chunks per document distribution.

These metrics let us tune chunk size/overlap scientifically.

### D. Storage + Index Layer
Adopt SQLite as canonical store with:
- `documents`, `pages_chunks`, `term_freq`, `term_df`, FTS virtual table,
- migration versioning in `meta`,
- WAL mode and cache pragmas,
- atomic per-document transactions.

Add incremental indexing improvements:
- keep current `(size, mtime)` fingerprint checks,
- optional stronger fingerprint mode (hash on demand) for edge cases,
- dedupe traversal input paths before indexing batch.

### E. Retrieval + Ranking Layer
Use one consistent two-stage strategy:
1. FTS5 candidate generation with filter-aware SQL,
2. BM25 reranking from `term_freq`/`term_df`.

Then enforce correctness upgrades:
- fallback retrieval must honor all active filters,
- strict input validation for typed filters (e.g., year),
- deterministic scoring normalization and tie-break ordering.

Future extension seam:
- add optional embedding reranker as a **third phase**, disabled by default, packaged separately.

### F. Application Layer (UI + CLI + Automation)
Expose one service contract used by both GUI and CLI:
- `index(paths, options)`
- `search(query, filters, options)`
- `list/remove/stats/history`

UI and CLI should be thin adapters over the same service functions so behavior never diverges.

Add machine-friendly CLI formats:
- JSON output for search/list/stats,
- stable exit codes.

---

## 3) Concrete Repository Consolidation Strategy

## Phase 0 — Stabilization Baseline
1. Freeze Lovable as `core baseline`.
2. Create `unification/` design docs and ADRs (architecture decisions).
3. Build acceptance test matrix (indexing, search relevance, filter correctness, OCR optional paths).

## Phase 1 — Module Inventory + Diff Mapping
1. Catalog each implementation (`Lovable`, `Claude`, `Kimi`, `Vibestral`, etc.) by subsystem:
   - parsers,
   - chunkers,
   - indexers,
   - searchers,
   - UI features,
   - CLI features.
2. Mark each candidate as:
   - **Adopt now**,
   - **Adapt later**,
   - **Discard**.
3. Require evidence for adoption: benchmark gain, reliability gain, or UX gain.

## Phase 2 — Service-Core Extraction
1. Extract a `core service` package containing all business logic.
2. Ensure GUI and CLI both call service APIs only.
3. Eliminate duplicated logic in UI event handlers and CLI commands.

## Phase 3 — Retrieval Correctness Hardening
1. Normalize filter handling in all retrieval paths (FTS and fallback).
2. Add robust query sanitization and typed filter validation.
3. Add property-based tests for parser and ranking invariants.
4. Add golden-query relevance checks on a fixed evaluation corpus.

## Phase 4 — Performance + Scale Pass
1. Profile indexing and search latency on increasing corpus sizes.
2. Batch DB writes and tune SQL paths where hotspots appear.
3. Add optional background index queue and cancellation support.
4. Add cache invalidation semantics for synonyms/settings.

## Phase 5 — UX Unification
1. Merge best UX features from all variants into one coherent interface:
   - keyboard shortcuts,
   - theme switching,
   - search history,
   - filter sidebar,
   - progress + status telemetry.
2. Keep UI lightweight (Tkinter) for offline footprint goals.

## Phase 6 — Packaging + Distribution
1. Standardize single build pipeline (`pyinstaller.spec`).
2. Keep OCR external dependency optional.
3. Publish reproducible build instructions and release checklist.

---

## 4) Data Contracts and API Contracts (Must Be Stable)

### Document contract
- `id, title, file_path, file_type, page_count, size, mtime, indexed_at, metadata`

### Chunk contract
- `chunk_id, doc_id, unit_num/page_num, chunk_idx, section_header, content, token_count, prev_id, next_id`

### Search response contract
- `query, elapsed_ms, results[], facets{}, debug(optional)`
- each result: `chunk_id, doc_id, title, file_path, location, snippet, score, score_breakdown(optional)`

### Config contract
- chunking params,
- BM25 params,
- candidate limit,
- fallback strategy,
- synonym source,
- optional OCR flags.

A stable contract layer is the key to safely combining code from multiple versions without regressions.

---

## 5) Quality Gates for “Truly Integrated” (Not Superficial)

A change is considered integrated only if all are true:
1. **Behavioral parity:** GUI and CLI return equivalent search results for same inputs.
2. **Schema safety:** migrations run cleanly on old and fresh DBs.
3. **Relevance integrity:** no statistically significant drop on benchmark query set.
4. **Performance budget:** search and indexing remain within target latency/memory bands.
5. **Offline guarantee:** no hidden network dependency.
6. **Package size guard:** distribution artifact stays within budget.

---

## 6) Implementation Blueprint for You (Practical Roadmap)

### Sprint 1 (Core correctness)
- Consolidate filter handling (including fallback),
- validate typed filters,
- add test coverage for malformed input and fallback correctness.

### Sprint 2 (Service unification)
- Introduce shared service layer,
- refactor UI/CLI to call service APIs,
- add JSON CLI contract tests.

### Sprint 3 (Performance)
- benchmark + profile,
- optimize hot SQL paths,
- add structured internal telemetry.

### Sprint 4 (Feature merge)
- import selected UX improvements from other variants,
- merge vetted parser/chunker enhancements,
- run full regression matrix.

### Sprint 5 (Release hardening)
- package-size optimization,
- release automation,
- final acceptance tests across sample corpora.

---

## 7) Final Integrated Vision
You end with one cohesive application that:
- remains **offline-first** and lightweight,
- supports **PDF + EPUB + optional OCR** robustly,
- provides **fast, relevant retrieval** (FTS5 + BM25 + safe fallback),
- keeps a **single source of truth** for search/index behavior across GUI and CLI,
- is **extensible** for future hybrid reranking without breaking the offline core.

This approach avoids the “easy way out” (choosing a single folder and ignoring the rest). Instead, it uses the entire repository as a feature and design reservoir, while enforcing a strict integration discipline so the final product is coherent, testable, and optimized for your primary use case: **uploading documents and querying their text accurately and quickly**.
