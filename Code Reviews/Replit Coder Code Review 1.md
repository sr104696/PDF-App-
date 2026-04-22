# Replit Coder Code Review 1

## Scope
Reviewed the **`Lovable/`** implementation of PDF Intelligence — the variant
selected as the runtime for the Replit environment because it has the most
complete structure (layered `src/` package, README, ARCHITECTURE.md, tests).
Focus areas: search/index correctness, ingestion robustness, web-wrapping
implications (`Lovable/web_app.py`), thread/connection safety, security of
upload/file paths, and small consistency issues. The Tkinter UI was inspected
but is out of scope for hardening since it is no longer the runtime entry point.

## High-Level Assessment
The codebase is small, modular, well-commented, and reads like a deliberate
v2 rewrite. The two-phase retrieval (FTS5 candidates → pure-Python BM25 rerank)
is the right architecture, transactions and `PRAGMA` settings are sensible, and
the chunker/tokenizer have thoughtful fallbacks. The biggest risks are
concentrated in:
1. Filter handling consistency between primary and fallback search paths,
2. SQLite connection sharing across threads (more visible now that a Flask
   server fronts the engine),
3. Upload path handling and resource limits in the new web layer,
4. A handful of brittle parsing edges (year coercion, FTS expression building).

None of these are blocking; all are fixable in small, targeted patches.

---

## Findings

### 1) Filters are silently dropped in the fuzzy fallback path
- **Severity:** High
- **Where:** `src/search/searcher.py` — `_fuzzy_fallback(...)`
- **Why it matters:** When the primary FTS query returns zero candidates (typo,
  punctuation-heavy query, etc.), `search()` calls `_fuzzy_fallback(conn, pq.tokens, CANDIDATE_LIMIT, filters)`.
  The function accepts `filters` but neither branch (the `LIKE` scan nor the
  `LIMIT 5000` rapidfuzz scan) actually applies them. Users who select a
  `file_type=epub` or `author=...` facet can therefore receive results that
  violate the active filter — a correctness regression versus the FTS path.
- **Fix:** Lift the predicate-building snippet from `_fetch_candidates` into a
  small helper (`_apply_filters(where, params, filters)`) and call it from both
  `_fetch_candidates` and `_fuzzy_fallback`. Thread the same `WHERE` clause
  through the two fallback SQL statements.

### 2) Single SQLite connection shared across Flask worker threads
- **Severity:** High (newly relevant under the web wrapper)
- **Where:** `Lovable/web_app.py` — module-level `_conn = open_db(DB_PATH)`,
  guarded by a single `_db_lock`.
- **Why it matters:** `open_db` uses `check_same_thread=False`, so cross-thread
  use is technically permitted, but a single global lock serializes *all*
  requests — including read-only searches — behind any in-progress upload/index.
  An upload of a large PDF will block every search for the duration of indexing.
  It also defeats Gunicorn's `--workers=2` for read concurrency since each
  worker is one process anyway, but the in-process serialization remains within
  each worker.
- **Fix options (pick one):**
  1. Use a thread-local connection (`threading.local()`-cached `open_db`) so
     concurrent reads run in parallel; SQLite WAL mode (already enabled) makes
     this safe.
  2. Or switch to a tiny connection pool and only take an exclusive lock around
     `index_paths` / `rebuild_term_df` (writers).

### 3) Upload endpoint trusts client filename for the on-disk path
- **Severity:** High
- **Where:** `Lovable/web_app.py` — `api_upload()` does
  `safe = Path(f.filename).name; dest = UPLOAD_DIR / safe`.
- **Why it matters:** `Path(...).name` strips directory components on POSIX, but
  Windows-style filenames (`..\evil.pdf`) and reserved names slip through, and
  collisions silently overwrite previously uploaded files of the same name —
  reindexing a different document under the same `documents.file_path` key.
  There is also no per-file size cap (only the global `MAX_CONTENT_LENGTH`).
- **Fix:**
  * Use `werkzeug.utils.secure_filename` (already a Flask transitive dep).
  * Disambiguate collisions (e.g. append a short hash or mtime) instead of
    overwriting.
  * Validate magic bytes (PDF starts `%PDF`, EPUB is a ZIP with `mimetype`
    `application/epub+zip`) — extension whitelisting alone is weak.

### 4) `year` filter is `int(...)`-coerced without validation
- **Severity:** Medium
- **Where:** `src/search/searcher.py` — `_fetch_candidates`
- **Why it matters:** `params.append(int(filters["year"]))` raises `ValueError`
  on `""`, `"2020s"`, or any malformed input from the UI/web layer. Today the
  Tkinter UI happens to feed clean values, but the new HTTP surface makes this
  a 500-error vector.
- **Fix:** Validate with `try: y = int(filters["year"])` and either drop the
  filter with a `log.warning` or return a typed validation error to the caller.

### 5) FTS expression builder drops legitimate non-ASCII tokens
- **Severity:** Medium
- **Where:** `src/search/query_parser.py` — `_build_fts`
  uses `if t.isalnum()`, but the tokenizer (`_WORD_RE`) is `re.UNICODE` and
  emits accented and Unicode word characters.
- **Why it matters:** Accented terms (`café`, `naïve`, German umlauts) survive
  tokenization but are then filtered out of the FTS query, so they only appear
  via the rapidfuzz fallback. Combined with finding 1, that means accented
  searches with active filters effectively ignore the filters too.
- **Fix:** Replace `isalnum()` with a tighter check that allows Unicode word
  chars but escapes/strips FTS5 syntax characters (`"`, `(`, `)`, `*`, `:`, `^`,
  `+`, `-`, `.`). Easiest: build a small `_FTS_SAFE = re.compile(r"^\w+$", re.U)`
  and use that.

### 6) `_make_snippet` is case-folded incorrectly for non-ASCII
- **Severity:** Low
- **Where:** `src/search/searcher.py` — uses `text.lower()` and `.find` for
  query token positioning. Works for ASCII, but `casefold()` is the correct
  primitive for case-insensitive matching across Unicode (e.g. German `ß` →
  `ss`). Snippets occasionally fall back to the head-of-text on perfectly valid
  hits.
- **Fix:** Switch both sides of the comparison to `casefold()`.

### 7) Synonym token explosion not bounded
- **Severity:** Low
- **Where:** `src/search/query_parser.py` — `pq.synonyms` accumulates every
  whitespace-split sub-stem of every synonym entry. With a user-customized
  `data/synonyms.json`, a single query token can generate dozens of stems,
  which then get fed into `_df_lookup` and `_tf_lookup` `IN (...)` queries.
- **Why it matters:** Performance cliff and a very large `IN` clause if the
  synonym file grows. Also dilutes the additive boost.
- **Fix:** Cap synonym set to e.g. 8 stems per query, prefer the shorter/more
  common variants, and de-duplicate against `pq.stems` before the SQL builds
  (already done; just add the cap).

### 8) `_record_history` swallows every exception silently
- **Severity:** Low
- **Where:** `src/search/searcher.py`
- **Why it matters:** Useful as a non-fatal write, but `except Exception: pass`
  hides locking, schema, and disk-full conditions that should at least surface
  in logs.
- **Fix:** `log.debug("history write failed", exc_info=True)`.

### 9) `chunker._pack_sentences` recomputes `count_tokens` quadratically
- **Severity:** Low (perf only, large pages)
- **Where:** `src/core/chunker.py` — for every sentence in the carry-over loop,
  it re-scans the sentence with the regex via `count_tokens(s)`. On long pages
  this becomes O(n²) in sentence length.
- **Fix:** Memoize `count_tokens` per sentence in a parallel list, or inline the
  carry as `(sentence, n_tokens)` tuples.

### 10) `chunk_page` uses a 60-char prefix `find` to recover offsets
- **Severity:** Low (data-quality)
- **Where:** `src/core/chunker.py` — `text.find(piece[:60], cursor)` to derive
  `start_char/end_char`. After whitespace normalization or repeated boilerplate
  (page headers/footers), this can match the wrong occurrence and produce
  nonsensical offsets, which then poison `chunk_id` (offsets feed the SHA1).
  Stable IDs are no longer stable in that case across re-indexes.
- **Fix:** Track an exact running cursor while building chunks (the chunker has
  the original sentence list — it can sum sentence lengths + spacers instead of
  re-searching) so offsets are always exact.

### 11) `index_paths` writes inside a long transaction *outside* `BEGIN`
- **Severity:** Low (subtle correctness)
- **Where:** `src/index/indexer.py` — `rebuild_term_df` and the per-file
  `index_file` each open their own `BEGIN`, but `index_paths` does not wrap the
  whole batch. Combined with `isolation_level=None` (autocommit) on the
  connection, partial-batch failures leave the corpus in an inconsistent state
  with stale `term_df`. The function also only calls `rebuild_term_df` once at
  the end, so an early exception (caught outside the loop) skips the rebuild
  entirely after some files were indexed.
- **Fix:** Move `rebuild_term_df` into a `try/finally` so it always runs after
  *some* files were indexed, and consider per-file checkpointing instead.

### 12) `pdf_parser.extract_pages` can re-open the PDF twice for OCR
- **Severity:** Low (perf)
- **Where:** `src/core/pdf_parser.py` — `_ocr_page` opens the entire PDF for
  every page that needs OCR.
- **Fix:** When `ocr=True`, pass the open `pdfplumber.PDF` handle through, or
  collect OCR-needed indices first and process them in one pass.

### 13) `_lazy_nltk.ensure_punkt` re-raises on a download failure
- **Severity:** Low
- **Where:** `src/_lazy_nltk.py` — the comment says "silently fall back" but the
  `except Exception: raise` re-raises, which is then caught in `_try_punkt()`
  and disables Punkt for the whole process. The end-state is correct, but the
  comment misleads readers debugging the offline path.
- **Fix:** Either change the comment or drop the `raise` in favor of `_DONE = False`
  with a debug log.

### 14) Web template — minor production-readiness items
- **Severity:** Low
- **Where:** `Lovable/web_app.py`
- **Issues:**
  * Inline HTML/JS via `render_template_string` mixes Jinja and JS escaping
    rules; an earlier version produced an "Unexpected string" SyntaxError due
    to a `\"` literal that Python decoded before Jinja saw it. The current
    file fixes that, but extracting the page into `templates/index.html`
    eliminates the whole class of bug.
  * No CSRF protection on `POST /api/upload` (Flask doesn't add it by default).
    Acceptable for a single-user offline tool, but worth noting if the app is
    ever exposed beyond `0.0.0.0` on a private network.
  * Per-file size limit: only the global `MAX_CONTENT_LENGTH = 100 MB` exists;
    a single 100 MB file passes, ten 50 MB files do not. Document the limit in
    the UI or add a friendlier 413 handler.

### 15) `documents.file_path` is `UNIQUE` but uploads can change paths
- **Severity:** Low (consistency)
- **Where:** `src/index/schema.py` + upload flow.
- **Why it matters:** Re-uploading the same file from a different directory
  creates a *new* `documents` row even though the content is identical, since
  the unique key is the path. A content hash (already implemented in
  `file_sha1`) would be a better dedupe key for the web flow.

---

## Positive Notes
- Two-phase retrieval (FTS5 → BM25) is implemented cleanly and is easy to read.
- BM25 implementation is mathematically correct, with sane IDF smoothing and
  min-max normalization.
- Connection setup (`open_db`) uses WAL, sensible `synchronous=NORMAL`, and a
  bounded page cache — good defaults for the offline use case.
- Indexer uses explicit `BEGIN`/`COMMIT`/`ROLLBACK` per file, which gives
  per-file atomicity even though the batch isn't atomic.
- Chunker preserves prev/next links and section headers, enabling future
  context-window features without a re-index.
- Lazy NLTK loader and the snowball/identity stemmer fallback both keep cold
  start fast and offline-safe.
- The CLI uses `argparse` with subcommands — solid baseline.
- Web wrapper added for Replit (`web_app.py`) is intentionally thin; it imports
  `src.index` and `src.search` directly without forking logic, which keeps the
  desktop and web entry points behaviorally identical.

---

## Suggested Next Steps (priority order)
1. **Filter parity in fallback search** (Finding 1) — highest user-visible bug.
2. **Per-thread SQLite connections** (Finding 2) — unlocks read concurrency
   under the web server.
3. **Harden upload path & validation** (Finding 3) — biggest safety win for
   the new HTTP surface.
4. **Validate `year` and tighten FTS token whitelist** (Findings 4 & 5).
5. **Tests for:** fallback+filters parity, malformed `year`, accented-token
   search, upload collisions, concurrent search-during-index.
6. Cleanup pass for findings 6–13 in a single low-risk PR.
