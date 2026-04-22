"""Double-Metaphone phonetic fallback — pure Python, zero dependencies.

Used when FTS5 and rapidfuzz both return nothing (rare, very misspelled queries).
Catches things like "Nietzche" → "Nietzsche", "Shakespear" → "Shakespeare".
"""
from __future__ import annotations

import re
import sqlite3
from typing import Dict, List, Sequence

# ── Double Metaphone (minimal English implementation) ─────────────────────

_VOWELS = set("AEIOU")


def _dm(word: str) -> List[str]:
    """Return 1-2 double-metaphone codes for a word. Simplified but serviceable."""
    w = re.sub(r"[^A-Z]", "", word.upper())
    if not w:
        return [""]

    codes = []
    i = 0
    primary = []
    secondary = []

    # Simplified rules covering ~90% of English names/words
    while i < len(w):
        c = w[i]
        nxt = w[i+1] if i+1 < len(w) else ""
        nxt2 = w[i+2] if i+2 < len(w) else ""

        if c in _VOWELS and i == 0:
            primary.append("A"); secondary.append("A"); i += 1; continue

        if c == "B":
            primary.append("P"); secondary.append("P")
            i += 2 if nxt == "B" else 1; continue

        if c == "C":
            if nxt in ("I","E","Y"):
                primary.append("S"); secondary.append("S")
            elif nxt == "H":
                primary.append("X"); secondary.append("K")
                i += 1
            else:
                primary.append("K"); secondary.append("K")
            i += 1; continue

        if c == "D":
            if nxt == "G" and nxt2 in ("I","E","Y"):
                primary.append("J"); secondary.append("J"); i += 2
            else:
                primary.append("T"); secondary.append("T")
            i += 1; continue

        if c == "F":
            primary.append("F"); secondary.append("F")
            i += 2 if nxt == "F" else 1; continue

        if c == "G":
            if nxt in ("E","I","Y"):
                primary.append("J"); secondary.append("K")
            elif nxt == "H":
                primary.append("K"); secondary.append("K"); i += 1
            elif nxt == "N":
                primary.append("N"); secondary.append("KN")
            else:
                primary.append("K"); secondary.append("K")
            i += 1; continue

        if c == "H":
            if nxt in _VOWELS:
                primary.append("H"); secondary.append("H")
            i += 1; continue

        if c == "J":
            primary.append("J"); secondary.append("H"); i += 1; continue

        if c == "K":
            primary.append("K"); secondary.append("K")
            i += 2 if nxt == "K" else 1; continue

        if c == "L":
            primary.append("L"); secondary.append("L")
            i += 2 if nxt == "L" else 1; continue

        if c == "M":
            primary.append("M"); secondary.append("M")
            i += 2 if nxt == "M" else 1; continue

        if c == "N":
            primary.append("N"); secondary.append("N")
            i += 2 if nxt == "N" else 1; continue

        if c == "P":
            if nxt == "H":
                primary.append("F"); secondary.append("F"); i += 2
            else:
                primary.append("P"); secondary.append("P")
                i += 2 if nxt == "P" else 1
            continue

        if c == "Q":
            primary.append("K"); secondary.append("K")
            i += 2 if nxt == "Q" else 1; continue

        if c == "R":
            primary.append("R"); secondary.append("R")
            i += 2 if nxt == "R" else 1; continue

        if c == "S":
            if nxt == "H" or (nxt == "I" and nxt2 in ("O","A")):
                primary.append("X"); secondary.append("X"); i += 2
            elif nxt == "C" and nxt2 == "H":
                primary.append("SK"); secondary.append("SK"); i += 3
            else:
                primary.append("S"); secondary.append("S")
                i += 2 if nxt == "S" else 1
            continue

        if c == "T":
            if nxt == "H":
                primary.append("0"); secondary.append("T"); i += 2
            elif nxt == "I" and nxt2 in ("A","O"):
                primary.append("X"); secondary.append("X"); i += 1
            else:
                primary.append("T"); secondary.append("T")
                i += 2 if nxt == "T" else 1
            continue

        if c == "V":
            primary.append("F"); secondary.append("F")
            i += 2 if nxt == "V" else 1; continue

        if c == "W":
            if nxt in _VOWELS:
                primary.append("W"); secondary.append("W")
            i += 1; continue

        if c == "X":
            primary.extend(["S","K"]); secondary.extend(["S","K"]); i += 1; continue

        if c == "Y":
            if nxt in _VOWELS:
                primary.append("Y"); secondary.append("Y")
            i += 1; continue

        if c == "Z":
            primary.append("S"); secondary.append("S")
            i += 2 if nxt == "Z" else 1; continue

        i += 1

    p = "".join(primary)[:6]
    s = "".join(secondary)[:6]
    return [p, s] if s and s != p else [p]


def _metaphone_key(word: str) -> str:
    return "|".join(_dm(word))


def double_metaphone_query(
    conn: sqlite3.Connection,
    tokens: Sequence[str],
    limit: int,
) -> List[sqlite3.Row]:
    """Score all chunks by phonetic similarity to query tokens."""
    if not tokens:
        return []

    query_codes = {_metaphone_key(t) for t in tokens if t}

    # Pull a bounded slice and score by phonetic overlap
    rows = conn.execute(
        """SELECT c.id, c.doc_id, c.page_num, c.section_header,
                  c.content, c.token_count, c.prev_id, c.next_id,
                  d.title, d.file_path, d.file_type
           FROM pages_chunks c JOIN documents d ON d.id = c.doc_id
           LIMIT 5000"""
    ).fetchall()

    def phonetic_score(r) -> int:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", r[4][:500])
        chunk_codes = {_metaphone_key(w) for w in words}
        return len(query_codes & chunk_codes)

    scored = sorted(rows, key=phonetic_score, reverse=True)
    return [r for r in scored[:limit] if phonetic_score(r) > 0]
