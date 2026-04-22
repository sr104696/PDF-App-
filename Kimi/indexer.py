"""
SQLite schema, incremental indexing, BM25 stat caching, facet aggregation.
"""
import sqlite3
import os
from typing import List, Dict, Optional, Set
from dataclasses import asdict

from chunker import Chunk
import utils

class Indexer:
    def __init__(self, db_path: str = "pdf_searcher.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    # -----------------------------------------------------------------------
    # Schema
    # -----------------------------------------------------------------------
    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                filePath TEXT UNIQUE,
                pageCount INTEGER,
                indexedAt TEXT,
                fileSize INTEGER,
                author TEXT,
                year INTEGER,
                language TEXT,
                fileType TEXT,
                collection TEXT,
                fileMtime INTEGER,
                totalTokens INTEGER
            );

            CREATE TABLE IF NOT EXISTS pages_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                docId INTEGER,
                pageNum INTEGER,
                chunkId TEXT UNIQUE,
                content TEXT,
                sectionHeader TEXT,
                startChar INTEGER,
                endChar INTEGER,
                tokenCount INTEGER,
                prevId TEXT,
                nextId TEXT,
                FOREIGN KEY(docId) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS term_freq (
                docId INTEGER,
                chunkId TEXT,
                term TEXT,
                tf INTEGER,
                PRIMARY KEY(docId, chunkId, term),
                FOREIGN KEY(docId) REFERENCES documents(id),
                FOREIGN KEY(chunkId) REFERENCES pages_chunks(chunkId)
            );

            CREATE TABLE IF NOT EXISTS term_df (
                term TEXT PRIMARY KEY,
                df INTEGER
            );

            CREATE TABLE IF NOT EXISTS doc_tags (
                docId INTEGER,
                tag TEXT,
                PRIMARY KEY(docId, tag),
                FOREIGN KEY(docId) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                timestamp TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
                content, chunkId UNINDEXED, docId UNINDEXED,
                content='pages_chunks', content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS pages_chunks_ai AFTER INSERT ON pages_chunks BEGIN
                INSERT INTO fts_chunks(rowid, content, chunkId, docId)
                VALUES (new.id, new.content, new.chunkId, new.docId);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_chunks_ad AFTER DELETE ON pages_chunks BEGIN
                INSERT INTO fts_chunks(fts_chunks, rowid, content, chunkId, docId)
                VALUES ('delete', old.id, old.content, old.chunkId, old.docId);
            END;
        """)
        self.conn.commit()

    # -----------------------------------------------------------------------
    # Public: index / re-index
    # -----------------------------------------------------------------------
    def index_document(self, file_path: str, collection: str = "",
                       progress_callback=None) -> dict:
        result = {"success": False, "pagesIndexed": 0, "chunksIndexed": 0}
        ext = os.path.splitext(file_path)[1].lower()

        try:
            mtime = int(os.path.getmtime(file_path))
            size = os.path.getsize(file_path)

            # Incremental check
            row = self.conn.execute(
                "SELECT id, fileMtime FROM documents WHERE filePath=?",
                (file_path,)
            ).fetchone()

            if row and row[1] >= mtime:
                return {"success": True, "message": "Already up to date"}

            # Extract
            if ext == ".pdf":
                from pdf_parser import extract_pdf_text, has_extractable_text, ocr_pdf
                if not has_extractable_text(file_path):
                    # We do NOT auto-OCR; user must opt-in via Tools.
                    # But we still index whatever little text exists.
                    pass
                pages, meta = extract_pdf_text(file_path)
                ftype = "pdf"
            elif ext == ".epub":
                from pdf_parser import extract_epub_text
                pages, meta = extract_epub_text(file_path)
                ftype = "epub"
            else:
                raise ValueError("Unsupported file type")

            title = meta.get("title") or os.path.basename(file_path)
            author = meta.get("author", "")
            year = self._extract_year(title)

            # Insert / replace document
            if row:
                doc_id = row[0]
                self.conn.execute("DELETE FROM pages_chunks WHERE docId=?", (doc_id,))
                self.conn.execute("DELETE FROM term_freq WHERE docId=?", (doc_id,))
                self.conn.execute("""
                    UPDATE documents SET title=?, pageCount=?, indexedAt=datetime('now'),
                    fileSize=?, author=?, year=?, fileType=?, collection=?, fileMtime=?, totalTokens=?
                    WHERE id=?
                """, (title, len(pages), size, author, year, ftype, collection, mtime, 0, doc_id))
            else:
                cur = self.conn.execute("""
                    INSERT INTO documents (title,filePath,pageCount,indexedAt,fileSize,author,year,fileType,collection,fileMtime,totalTokens)
                    VALUES (?,?,?,datetime('now'),?,?,?,?,?,?,?)
                """, (title, file_path, len(pages), size, author, year, ftype, collection, mtime, 0))
                doc_id = cur.lastrowid

            # Chunk
            from chunker import chunk_document
            chunks = chunk_document(doc_id, file_path, pages)
            total_tokens = 0

            for ch in chunks:
                self.conn.execute("""
                    INSERT INTO pages_chunks (docId,pageNum,chunkId,content,sectionHeader,startChar,endChar,tokenCount,prevId,nextId)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (ch.doc_id, ch.page_num, ch.chunk_id, ch.content, ch.section_header,
                      ch.start_char, ch.end_char, ch.token_count, ch.prev_id, ch.next_id))
                total_tokens += ch.token_count

            self._rebuild_term_freq(doc_id, chunks)
            self.conn.execute("UPDATE documents SET totalTokens=? WHERE id=?", (total_tokens, doc_id))
            self.conn.commit()

            result.update(success=True, docId=doc_id, pagesIndexed=len(pages), chunksIndexed=len(chunks))
        except Exception as exc:
            self.conn.rollback()
            result["error"] = str(exc)
        return result

    # -----------------------------------------------------------------------
    # Term frequency / doc frequency maintenance
    # -----------------------------------------------------------------------
    def _rebuild_term_freq(self, doc_id: int, chunks: List[Chunk]):
        # Decrement df for old terms
        old_terms: Set[str] = set()
        cur = self.conn.execute("SELECT DISTINCT term FROM term_freq WHERE docId=?", (doc_id,))
        for r in cur:
            old_terms.add(r[0])

        self.conn.execute("DELETE FROM term_freq WHERE docId=?", (doc_id,))

        new_doc_terms: Set[str] = set()
        rows = []
        for ch in chunks:
            toks = utils.remove_stopwords(utils.tokenize(ch.content))
            stems = utils.stem_tokens(toks)
            tf: Dict[str, int] = {}
            for s in stems:
                tf[s] = tf.get(s, 0) + 1
                new_doc_terms.add(s)
            for term, c in tf.items():
                rows.append((doc_id, ch.chunk_id, term, c))

        if rows:
            self.conn.executemany(
                "INSERT INTO term_freq (docId,chunkId,term,tf) VALUES (?,?,?,?)",
                rows
            )

        removed = old_terms - new_doc_terms
        added = new_doc_terms - old_terms

        for t in removed:
            self.conn.execute("UPDATE term_df SET df = df - 1 WHERE term=? AND df>0", (t,))
            self.conn.execute("DELETE FROM term_df WHERE term=? AND df<=0", (t,))
        for t in added:
            self.conn.execute(
                "INSERT INTO term_df (term,df) VALUES (?,1) ON CONFLICT(term) DO UPDATE SET df=df+1",
                (t,)
            )

    # -----------------------------------------------------------------------
    # Stats for BM25
    # -----------------------------------------------------------------------
    def get_corpus_stats(self) -> Dict[str, float]:
        cur = self.conn.execute("SELECT COUNT(*), AVG(totalTokens) FROM documents")
        n, avgdl = cur.fetchone()
        return {"N": n or 0, "avgdl": avgdl or 0.0}

    def get_doc_freq(self, term: str) -> int:
        r = self.conn.execute("SELECT df FROM term_df WHERE term=?", (term,)).fetchone()
        return r[0] if r else 0

    # -----------------------------------------------------------------------
    # Facet aggregation
    # -----------------------------------------------------------------------
    def get_facets(self, doc_ids: Optional[Set[int]] = None) -> Dict[str, Dict[str, int]]:
        facets: Dict[str, Dict[str, int]] = {"author": {}, "year": {}, "fileType": {}, "tags": {}}
        id_filter = ""
        params: tuple = ()
        if doc_ids:
            ph = ",".join("?" * len(doc_ids))
            id_filter = f"WHERE id IN ({ph})"
            params = tuple(doc_ids)

        for field in ("author", "year", "fileType"):
            sql = f"SELECT {field}, COUNT(*) FROM documents {id_filter} GROUP BY {field}"
            for val, cnt in self.conn.execute(sql, params):
                if val is not None:
                    facets[field][str(val)] = cnt

        tag_sql = f"""
            SELECT tag, COUNT(*) FROM doc_tags
            WHERE docId IN (SELECT id FROM documents {id_filter})
            GROUP BY tag
        """
        for val, cnt in self.conn.execute(tag_sql, params):
            facets["tags"][val] = cnt

        return facets

    # -----------------------------------------------------------------------
    # History
    # -----------------------------------------------------------------------
    def save_history(self, query: str):
        self.conn.execute("INSERT INTO search_history (query,timestamp) VALUES (?,datetime('now'))", (query,))
        self.conn.execute("DELETE FROM search_history WHERE id NOT IN (SELECT id FROM search_history ORDER BY timestamp DESC LIMIT 10)")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    @staticmethod
    def _extract_year(text: str) -> Optional[int]:
        m = __import__('re').search(r'\b(19|20)\d{2}\b', text or "")
        return int(m.group(0)) if m else None
