# tests/test_smoke.py
# Smoke tests: import all modules, run chunker + BM25 math, open in-memory DB.
"""Smoke tests -- no PDF files required."""
from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

# Ensure project root is on path when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_imports():
    from src.utils.constants import APP_NAME, MAX_CHUNK_TOKENS, CHUNK_HARD_CAP
    assert APP_NAME
    assert MAX_CHUNK_TOKENS == 512
    assert CHUNK_HARD_CAP == 800


def test_stemmer():
    from src.search.stemmer import stem
    # snowball stems "running" -> "run" or fallback -> "runn"; either is acceptable
    assert stem("running") in ("run", "runn")
    assert stem("libraries") in ("librari", "library")


def test_tokenizer():
    from src.core.tokenizer import word_tokens, count_tokens, sentences
    toks = word_tokens("Hello, world! This is a test.")
    assert "hello" in toks
    assert count_tokens("one two three") == 3
    sents = sentences("Hello world. How are you?")
    assert len(sents) >= 1


def test_chunker_basic():
    from src.core.chunker import chunk_page
    text = "This is sentence one. " * 30
    chunks = chunk_page(file_path="/fake/path.pdf", page_num=1, text=text)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.token_count <= 600  # allow slight overlap overshoot


def test_chunker_hard_cap():
    from src.core.chunker import chunk_page
    # Single very long "sentence" with no punctuation
    text = " ".join(["word"] * 1000)
    chunks = chunk_page(file_path="/fake/path.pdf", page_num=1, text=text)
    for c in chunks:
        assert c.token_count <= 900  # hard cap enforced


def test_bm25_math():
    from src.search.bm25 import idf, score_chunk, normalize, CorpusStats
    assert idf(100, 10) > 0
    assert idf(0, 0) == 0.0
    stats = CorpusStats(n_chunks=100, avg_dl=50.0)
    s = score_chunk(
        query_terms=["test"],
        tf_in_chunk={"test": 3},
        chunk_len=50,
        df_lookup={"test": 10},
        stats=stats,
    )
    assert s > 0
    normed = normalize([0.0, 0.5, 1.0])
    assert normed[0] == 0.0
    assert normed[2] == 1.0


def test_query_parser():
    from src.search.query_parser import parse
    pq = parse("what is machine learning")
    assert pq.intent == "definition"
    assert "machin" in pq.stems or "machine" in pq.tokens

    pq2 = parse('"exact phrase" test')
    assert pq2.phrases == ["exact phrase"]
    assert "test" in pq2.tokens


def test_schema_open():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    from src.index.schema import DDL
    conn.executescript(DDL)
    conn.execute("INSERT INTO documents (title, file_path, file_type, page_count, "
                 "file_size, file_mtime, indexed_at, total_tokens) "
                 "VALUES ('Test', '/tmp/test.pdf', 'pdf', 1, 100, 0.0, 0.0, 50)")
    row = conn.execute("SELECT title FROM documents").fetchone()
    assert row[0] == "Test"
    conn.close()


def test_file_hash():
    from src.utils.file_hash import chunk_id, doc_id
    cid = chunk_id("/some/file.pdf", 1, 0, 100)
    assert len(cid) == 40
    did = doc_id("/some/file.pdf")
    assert len(did) == 40
    # Stable: same inputs -> same output
    assert chunk_id("/some/file.pdf", 1, 0, 100) == cid


if __name__ == "__main__":
    test_imports()
    test_stemmer()
    test_tokenizer()
    test_chunker_basic()
    test_chunker_hard_cap()
    test_bm25_math()
    test_query_parser()
    test_schema_open()
    test_file_hash()
    print("All smoke tests passed.")
