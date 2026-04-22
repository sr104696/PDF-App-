# Codex's Work

## What was reviewed
- Search query parsing and expansion flow.
- FTS candidate generation and BM25 ranking path.
- Synonym loading and persistence behavior.

## Fixes and optimizations applied
1. **Synonym loading cache added**
   - Added an `lru_cache` to avoid re-reading `synonyms.json` on every query.
   - Added cache invalidation after `save_synonyms` so edits are reflected immediately.

2. **Query stemming path simplified**
   - Replaced `stem_text(w)[0]` with `stem_word(w)` for each term.
   - This avoids per-term tokenization overhead and removes a fragile indexing assumption.

3. **FTS query hardening + deterministic behavior**
   - Added term escaping for FTS syntax safety.
   - Changed deduplication to preserve term order (`dict.fromkeys`) for reproducibility.
   - Filters out empty escaped terms before assembling the MATCH expression.

4. **BM25 scoring query optimized**
   - Deduplicates candidate document IDs once.
   - Fetches document lengths once per search.
   - Fetches only non-zero term frequencies from `term_freq` for candidate docs.
   - Reduces repeated SQL join workload in the scoring loop.

## Validation commands run
- `python -m pytest -q` (repository has no pytest-discovered tests).
- `python tests/test_flow.py` (smoke script runs; PDF-generation path skipped due to missing reportlab dependency).
