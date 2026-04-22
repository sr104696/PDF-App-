"""
Query parsing, Snowball expansion, two-phase retrieval (FTS5 -> BM25), faceting.
"""
import math
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set

import utils
from indexer import Indexer

K1 = 1.2
B = 0.75

@dataclass
class SearchResult:
    doc_id: int
    title: str
    file_path: str
    page_num: int
    chunk_id: str
    snippet: str
    section_header: Optional[str]
    score: float
    citation: str

class Searcher:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self.conn = indexer.conn

    # -----------------------------------------------------------------------
    # Main entry
    # -----------------------------------------------------------------------
    def search(self, query: str, filters: Optional[Dict] = None, limit: int = 20) -> Tuple[List[SearchResult], Dict]:
        filters = filters or {}
        self.indexer.save_history(query)

        # 1. Parse & expand
        intent = self._detect_intent(query)
        clean = self._clean_query(query)
        tokens = utils.remove_stopwords(utils.tokenize(clean))
        if not tokens:
            return [], {}

        stems = utils.stem_tokens(tokens)
        expanded = set(stems)
        expanded.update(utils.expand_synonyms(stems))
        terms = list(expanded)

        # 2. Prefilter docs by facets
        candidate_doc_ids = self._prefilter_documents(filters)

        # 3. Candidate generation (FTS5)
        fts_query = " OR ".join(terms)
        if candidate_doc_ids is not None:
            if not candidate_doc_ids:
                return [], {}
            ph = ",".join("?" * len(candidate_doc_ids))
            sql = f"""
                SELECT c.docId, c.chunkId, c.content, c.pageNum, c.sectionHeader,
                       d.title, d.filePath
                FROM fts_chunks f
                JOIN pages_chunks c ON f.rowid = c.id
                JOIN documents d ON c.docId = d.id
                WHERE f.content MATCH ? AND c.docId IN ({ph})
                ORDER BY rank
                LIMIT 200
            """
            params = [fts_query] + list(candidate_doc_ids)
        else:
            sql = """
                SELECT c.docId, c.chunkId, c.content, c.pageNum, c.sectionHeader,
                       d.title, d.filePath
                FROM fts_chunks f
                JOIN pages_chunks c ON f.rowid = c.id
                JOIN documents d ON c.docId = d.id
                WHERE f.content MATCH ?
                ORDER BY rank
                LIMIT 200
            """
            params = [fts_query]

        rows = self.conn.execute(sql, params).fetchall()
        if not rows:
            return [], self.indexer.get_facets(candidate_doc_ids)

        # 4. BM25 rerank
        stats = self.indexer.get_corpus_stats()
        N, avgdl = stats["N"], stats["avgdl"] or 1.0

        scored: List[Tuple[float, tuple]] = []
        for row in rows:
            doc_id, chunk_id, content, page_num, section_header, title, file_path = row
            score = self._bm25(doc_id, chunk_id, terms, N, avgdl)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        # 5. Format
        results: List[SearchResult] = []
        for score, row in scored[:limit]:
            doc_id, chunk_id, content, page_num, section_header, title, file_path = row
            snippet = self._snippet(content, stems)
            citation = f"{title}, p. {page_num}"
            if section_header:
                citation += f", {section_header}"
            results.append(SearchResult(
                doc_id=doc_id, title=title, file_path=file_path,
                page_num=page_num, chunk_id=chunk_id,
                snippet=snippet, section_header=section_header,
                score=score, citation=citation
            ))

        result_doc_ids = {r.doc_id for r in results}
        facets = self.indexer.get_facets(result_doc_ids)
        return results, facets

    # -----------------------------------------------------------------------
    # BM25 (pure Python)
    # -----------------------------------------------------------------------
    def _bm25(self, doc_id: int, chunk_id: str, terms: List[str], N: int, avgdl: float) -> float:
        dl_row = self.conn.execute("SELECT totalTokens FROM documents WHERE id=?", (doc_id,)).fetchone()
        dl = dl_row[0] or 1

        score = 0.0
        for term in terms:
            tf_row = self.conn.execute(
                "SELECT tf FROM term_freq WHERE docId=? AND chunkId=? AND term=?",
                (doc_id, chunk_id, term)
            ).fetchone()
            tf = tf_row[0] if tf_row else 0
            df = self.indexer.get_doc_freq(term)

            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            denom = tf + K1 * (1.0 - B + B * (dl / avgdl))
            if denom <= 0:
                continue
            score += idf * (tf * (K1 + 1)) / denom
        return score

    # -----------------------------------------------------------------------
    # Query understanding
    # -----------------------------------------------------------------------
    def _detect_intent(self, query: str) -> Dict:
        q = query.lower()
        intent = {"type": "general", "wantsQuotes": False, "wantsDefinition": False}
        if any(x in q for x in ("quote", "said", "passage")):
            intent.update(type="quotes", wantsQuotes=True)
        elif any(x in q for x in ("define", "meaning", "what is")):
            intent.update(type="definition", wantsDefinition=True)
        return intent

    def _clean_query(self, query: str) -> str:
        fillers = ["find", "search", "show", "get", "give me", "look for",
                   "quotes about", "passages on", "definition of"]
        q = query.lower()
        for f in fillers:
            q = q.replace(f, "")
        return q.strip()

    # -----------------------------------------------------------------------
    # Facet prefilter
    # -----------------------------------------------------------------------
    def _prefilter_documents(self, filters: Dict) -> Optional[Set[int]]:
        if not filters:
            return None

        conditions: List[str] = []
        params: List = []
        for k, v in filters.items():
            if not v:
                continue
            if k in ("author", "fileType"):
                conditions.append(f"{k} = ?")
                params.append(v)
            elif k == "year":
                conditions.append("year = ?")
                params.append(int(v))

        doc_ids: Optional[Set[int]] = None

        if conditions:
            where = " AND ".join(conditions)
            cur = self.conn.execute(f"SELECT id FROM documents WHERE {where}", params)
            doc_ids = {r[0] for r in cur}

        if filters.get("tag"):
            cur = self.conn.execute("SELECT docId FROM doc_tags WHERE tag=?", (filters["tag"],))
            tag_ids = {r[0] for r in cur}
            if doc_ids is not None:
                doc_ids &= tag_ids
            else:
                doc_ids = tag_ids

        return doc_ids

    # -----------------------------------------------------------------------
    # Snippet formatter
    # -----------------------------------------------------------------------
    def _snippet(self, content: str, terms: List[str], radius: int = 80) -> str:
        low = content.lower()
        pos = -1
        for t in terms:
            pos = low.find(t)
            if pos != -1:
                break
        if pos == -1:
            return (content[:200] + "...") if len(content) > 200 else content

        start = max(0, pos - radius)
        end = min(len(content), pos + radius)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet
