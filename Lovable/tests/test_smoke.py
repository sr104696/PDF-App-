"""Smoke tests. Run with:  python -m pytest -q  (pytest not bundled)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.chunker import chunk_page          # noqa: E402
from src.core.tokenizer import word_tokens, count_tokens, sentences  # noqa: E402
from src.search import bm25, query_parser        # noqa: E402
from src.search.stemmer import stem              # noqa: E402
from src.index.migrations import open_db         # noqa: E402


SAMPLE = (
    "BM25 is a ranking function used by search engines. It estimates the relevance "
    "of documents to a given search query.\n\n"
    "Snowball stemmers reduce words to a common base. Running becomes run. "
    "This avoids the brittle suffix stripping that plagued early versions."
)


class TestTokenizer(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(word_tokens("Hello, World! 2024"), ["hello", "world"])

    def test_count(self):
        self.assertGreater(count_tokens(SAMPLE), 20)

    def test_sentences(self):
        s = sentences(SAMPLE)
        self.assertGreaterEqual(len(s), 3)


class TestStemmer(unittest.TestCase):
    def test_running(self):
        self.assertEqual(stem("running"), stem("run"))


class TestChunker(unittest.TestCase):
    def test_chunks(self):
        chunks = chunk_page(file_path="test.pdf", page_num=1, text=SAMPLE)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(c.token_count > 0 for c in chunks))


class TestQueryParser(unittest.TestCase):
    def test_basic(self):
        pq = query_parser.parse("what is BM25 ranking")
        self.assertEqual(pq.intent, "definition")
        self.assertIn("bm25", pq.tokens)

    def test_phrase(self):
        pq = query_parser.parse('find "search engine"')
        self.assertIn("search engine", pq.phrases)


class TestBM25(unittest.TestCase):
    def test_score(self):
        stats = bm25.CorpusStats(n_docs=100, avg_dl=120.0)
        s = bm25.score_chunk(
            query_terms=["bm25", "rank"],
            tf_in_chunk={"bm25": 3, "rank": 2},
            chunk_len=120,
            df_lookup={"bm25": 5, "rank": 30},
            stats=stats,
        )
        self.assertGreater(s, 0)


class TestEndToEnd(unittest.TestCase):
    def test_index_and_search(self):
        from src.core.chunker import Chunk
        from src.index import indexer
        from src.search import searcher

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "lib.db"
            conn = open_db(db)
            # Manually insert a fake document with one chunk.
            conn.execute("BEGIN")
            cur = conn.execute(
                """INSERT INTO documents
                   (title, file_path, file_type, page_count, file_size, file_mtime,
                    indexed_at, total_tokens) VALUES
                   ('Demo','/tmp/demo.pdf','pdf',1,1,1,1,0)""")
            doc_id = cur.lastrowid
            from src.index.indexer import _insert_chunk  # type: ignore
            ch = Chunk(id="abc", page_num=1, section=None, text=SAMPLE,
                       token_count=count_tokens(SAMPLE), start_char=0,
                       end_char=len(SAMPLE))
            _insert_chunk(conn, doc_id, 0, ch)
            conn.execute("COMMIT")
            indexer.rebuild_term_df(conn)

            resp = searcher.search(conn, "BM25 ranking")
            self.assertGreaterEqual(len(resp.results), 1)
            self.assertEqual(resp.results[0].title, "Demo")


if __name__ == "__main__":
    unittest.main()
