"""
test_flow.py — Smoke tests for the full index → search pipeline.

Runs without any real PDF files by creating a minimal in-memory test
database and injecting synthetic chunks directly.

Run with:
    python -m unittest tests.test_flow -v
"""
import os
import sys
import tempfile
import unittest

# Ensure project root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class TestTokenizer(unittest.TestCase):
    def test_tokenize_words(self):
        from src.core.tokenizer import tokenize_words
        tokens = tokenize_words("Hello, World! This is a TEST.")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
        self.assertIn("test", tokens)

    def test_count_words(self):
        from src.core.tokenizer import count_words
        self.assertEqual(count_words("one two three"), 3)

    def test_sentence_split_regex_fallback(self):
        from src.core.tokenizer import tokenize_sentences
        text = "First sentence. Second sentence! Third one."
        sents = tokenize_sentences(text)
        self.assertGreaterEqual(len(sents), 1)


class TestStemmer(unittest.TestCase):
    def test_stem_basic(self):
        from src.search.stemmer import stem_word
        # Snowball should reduce 'running' → 'run' (or similar stem)
        result = stem_word("running")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_stem_words_list(self):
        from src.search.stemmer import stem_words
        results = stem_words(["running", "happily", "beautiful"])
        self.assertEqual(len(results), 3)


class TestChunker(unittest.TestCase):
    def _make_page(self, text: str, page_num: int = 1):
        from src.core.pdf_parser import PageText
        return PageText(page_num=page_num, text=text, heading_hint="Test Section")

    def test_basic_chunk(self):
        from src.core.chunker import chunk_page
        page = self._make_page("This is a simple paragraph. " * 20)
        chunks = chunk_page(page, "/fake/path.pdf", "docid123")
        self.assertGreater(len(chunks), 0)
        for ch in chunks:
            self.assertLessEqual(ch.token_count, 550)  # allow small overlap

    def test_chunk_ids_stable(self):
        from src.core.chunker import chunk_page
        page = self._make_page("Stable id test paragraph. " * 10)
        c1 = chunk_page(page, "/fake/path.pdf", "docid123")
        c2 = chunk_page(page, "/fake/path.pdf", "docid123")
        ids1 = [c.chunk_id for c in c1]
        ids2 = [c.chunk_id for c in c2]
        self.assertEqual(ids1, ids2)

    def test_prev_next_links(self):
        from src.core.chunker import chunk_document, chunk_page
        from src.core.pdf_parser import PageText
        pages = [
            PageText(1, "A " * 600, "Section A"),
            PageText(2, "B " * 600, "Section B"),
        ]
        chunks = chunk_document(pages, "/fake/book.pdf", "docxxx")
        if len(chunks) > 1:
            self.assertNotEqual(chunks[0].next_id, "")


class TestQueryParser(unittest.TestCase):
    def test_phrase_extraction(self):
        from src.search.query_parser import parse
        pq = parse('"deep learning" optimizer')
        self.assertIn("deep learning", pq.phrases)
        self.assertIn("optim", pq.stemmed)  # 'optimizer' stems to 'optim'

    def test_stop_word_removal(self):
        from src.search.query_parser import parse
        pq = parse("what is the meaning of life")
        self.assertNotIn("what", pq.terms)
        self.assertNotIn("the", pq.terms)
        self.assertNotIn("is", pq.terms)

    def test_empty_query(self):
        from src.search.query_parser import parse
        pq = parse("   ")
        self.assertTrue(pq.is_empty())

    def test_fts_expression(self):
        from src.search.query_parser import parse
        pq = parse("neural networks")
        expr = pq.fts_expression()
        self.assertIn("*", expr)

    def test_intent_detection(self):
        from src.search.query_parser import parse
        pq = parse("define consciousness")
        self.assertEqual(pq.intent, "definition")


class TestBM25(unittest.TestCase):
    def test_normalize_empty(self):
        from src.search.bm25 import min_max_normalize
        self.assertEqual(min_max_normalize({}), {})

    def test_normalize_single(self):
        from src.search.bm25 import min_max_normalize
        result = min_max_normalize({"a": 5.0})
        self.assertEqual(result["a"], 1.0)

    def test_normalize_range(self):
        from src.search.bm25 import min_max_normalize
        result = min_max_normalize({"a": 0.0, "b": 10.0, "c": 5.0})
        self.assertAlmostEqual(result["a"], 0.0)
        self.assertAlmostEqual(result["b"], 1.0)
        self.assertAlmostEqual(result["c"], 0.5)


class TestFullPipeline(unittest.TestCase):
    """Integration test: create a real (temp) DB, index synthetic data, search."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test.db")

        # Initialise schema
        from src.index.schema import initialize_db
        initialize_db(self._db)

        # Insert a synthetic document and chunks
        from src.index.schema import get_db_connection
        from src.utils.file_hash import doc_id, chunk_id

        self._fp = "/fake/test_document.pdf"
        self._did = doc_id(self._fp)
        conn = get_db_connection(self._db)
        conn.execute(
            """
            INSERT INTO documents
                (id, title, filePath, pageCount, fileSize, fileType,
                 fileMtime, totalTokens, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self._did, "Test Document", self._fp, 5, 12345, "pdf", 1000.0, 150, "2023"),
        )
        # Two chunks with known content
        for i, text in enumerate([
            "The Okapi BM25 algorithm is a probabilistic information retrieval model.",
            "Neural networks and deep learning have transformed artificial intelligence research.",
        ]):
            cid = chunk_id(self._fp, 1, i * 200, (i + 1) * 200)
            conn.execute(
                """
                INSERT INTO pages_chunks
                    (id, docId, pageNum, chunkId, content, sectionHeader,
                     startChar, endChar, tokenCount, prevId, nextId)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cid, self._did, 1, cid, text, "Introduction",
                 i * 200, (i + 1) * 200, len(text.split()), None, None),
            )
            # term_freq
            from collections import Counter
            from src.core.tokenizer import tokenize_words
            from src.search.stemmer import stem_words
            stemmed = stem_words(tokenize_words(text))
            for term, tf in Counter(stemmed).items():
                conn.execute(
                    "INSERT OR IGNORE INTO term_freq(chunkId, docId, term, tf) VALUES (?, ?, ?, ?)",
                    (cid, self._did, term, tf),
                )
        conn.commit()
        conn.close()

        # Build term_df
        from src.index.indexer import rebuild_term_df
        rebuild_term_df(self._db)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_search_returns_results(self):
        from src.search.searcher import search
        response = search("BM25 probabilistic", db_path=self._db, save_history=False)
        self.assertGreater(len(response.results), 0)
        titles = [r.title for r in response.results]
        self.assertIn("Test Document", titles)

    def test_search_scores_normalised(self):
        from src.search.searcher import search
        response = search("BM25", db_path=self._db, save_history=False)
        for r in response.results:
            self.assertGreaterEqual(r.score, 0.0)
            self.assertLessEqual(r.score, 1.0 + 1e-9)

    def test_empty_query_returns_nothing(self):
        from src.search.searcher import search
        response = search("  ", db_path=self._db, save_history=False)
        self.assertEqual(len(response.results), 0)

    def test_search_history(self):
        from src.index.indexer import save_search_history, get_search_history
        save_search_history("test query", db_path=self._db)
        hist = get_search_history(db_path=self._db)
        self.assertIn("test query", hist)

    def test_facets_returned(self):
        from src.search.facets import all_facets
        facets = all_facets(db_path=self._db)
        self.assertIn("fileTypes", facets)
        self.assertIn("years", facets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
