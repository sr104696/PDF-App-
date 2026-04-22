# Codex Code Review 1

## Scope
Reviewed the **Lovable** implementation with emphasis on indexing/search correctness, CLI behavior, and fallback logic.

## High-Level Assessment
The codebase is generally clean and modular (separate `core`, `index`, `search`, and `ui` layers), and the existing test suite currently passes. The largest correctness risks are concentrated in search fallback behavior and input validation.

## Findings

### 1) Filters are ignored in fuzzy fallback search
- **Severity:** High
- **Why it matters:** If users apply metadata filters (for example `file_type`, `author`, `collection`, `year`), those constraints are respected in FTS mode but silently ignored in fallback mode. This can return results that violate the active filter constraints, which is a correctness issue.
- **Evidence:**
  - `search()` passes `filters` into `_fuzzy_fallback(...)` when there are no FTS candidates.
  - `_fuzzy_fallback(...)` receives a `filters` parameter but does not use it in either branch (`LIKE` fallback without `rapidfuzz`, or the bounded `LIMIT 5000` scan with `rapidfuzz`).
- **Recommendation:** Apply the same filter predicate-building logic used in `_fetch_candidates(...)` to the fallback SQL paths so fallback behavior remains semantically consistent with primary search behavior.

### 2) Invalid `year` filter can raise an unhandled exception
- **Severity:** Medium
- **Why it matters:** `_fetch_candidates(...)` casts `filters["year"]` to `int` without validation. Non-numeric input (e.g., empty string, malformed query parameter) will raise `ValueError` and can bubble up as an unexpected failure.
- **Evidence:** `params.append(int(filters["year"]))` has no guard.
- **Recommendation:** Validate/parsing-protect `year` before conversion. If invalid, either ignore the filter (with warning log) or return a typed validation error to the caller/UI.

### 3) Broad exception swallowing in search history write path
- **Severity:** Low
- **Why it matters:** `_record_history(...)` catches all exceptions and suppresses them with `pass`. This avoids user-facing failures, but it also hides operational issues (DB locks/corruption/schema drift) that should be diagnosable.
- **Evidence:** `except Exception: pass` in `_record_history(...)`.
- **Recommendation:** Keep non-fatal behavior, but log the exception at debug/warn level so silent failures can be observed during troubleshooting.

## Positive Notes
- The two-phase retrieval architecture (FTS candidate generation + BM25 rerank) is sensible and maintainable.
- Indexing uses explicit transactions and rollback paths, which is robust.
- Test smoke suite executes cleanly in current environment.

## Suggested Next Steps
1. Fix fallback filtering parity first (highest user-visible impact).
2. Add input validation for `year` in the filter pipeline.
3. Replace silent history exception swallow with low-noise logging.
4. Add tests for:
   - fallback + filters consistency,
   - malformed `year` handling,
   - history write failure observability.
