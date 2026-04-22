# src/search/query_parser.py
# Changes: Replaced Lovable's small FILLER_WORDS with Claude's comprehensive stop-word
# set; added intent detection patterns from Claude; kept Lovable's ParsedQuery dataclass
# and FTS5 expression builder; fixed all mojibake.
"""Query parser (sheet 21).

Responsibilities:
* Strip stop words.
* Detect intent flags: phrase queries ("..."), definition, comparison, example.
* Produce original tokens and stemmed tokens.
* Optionally produce synonym-expanded token set for soft boosting.
* Build FTS5 MATCH expression.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

from ..core.tokenizer import word_tokens
from ..utils.constants import FILLER_WORDS
from ..utils import synonyms
from .stemmer import stem

_PHRASE_RE = re.compile(r'"([^"]{1,200})"')
_DEFINE_RE = re.compile(
    r"^(?:define|definition of|what is|what's|meaning of)\s+(.+)$",
    re.IGNORECASE,
)

_INTENT_PATTERNS = {
    "definition": re.compile(r"\b(defin\w+|what\s+is|meaning\s+of|explain\w*)\b", re.I),
    "comparison":  re.compile(r"\b(compar\w*|versus|vs\.?|differ\w*|similar\w*)\b", re.I),
    "example":     re.compile(r"\b(example\w*|instance|illustrat\w*)\b", re.I),
    "quote":       re.compile(r"\b(quot\w*|said|says|stat\w+|phrase|passage)\b", re.I),
}


@dataclass
class ParsedQuery:
    raw: str
    tokens: List[str] = field(default_factory=list)
    stems: List[str] = field(default_factory=list)
    phrases: List[str] = field(default_factory=list)
    synonyms: Set[str] = field(default_factory=set)
    intent: str = "general"
    fts_query: str = ""

    def is_empty(self) -> bool:
        return not (self.tokens or self.phrases)


def _build_fts(tokens: List[str], phrases: List[str]) -> str:
    """Build an FTS5 MATCH expression. Phrases quoted, tokens prefix-matched."""
    parts: List[str] = []
    for ph in phrases:
        safe = ph.replace('"', '""')
        parts.append(f'"{safe}"')
    if tokens:
        parts.append(" OR ".join(f'{t}*' for t in tokens if t.isalnum()))
    return " AND ".join(p for p in parts if p)


def parse(raw: str, expand_synonyms: bool = True) -> ParsedQuery:
    pq = ParsedQuery(raw=raw or "")
    if not raw or not raw.strip():
        return pq
    text = raw.strip()

    # Intent detection
    m = _DEFINE_RE.match(text)
    if m:
        pq.intent = "definition"
        text = m.group(1)
    else:
        for name, pat in _INTENT_PATTERNS.items():
            if pat.search(text):
                pq.intent = name
                break

    # Extract quoted phrases
    phrases = _PHRASE_RE.findall(text)
    if phrases:
        pq.phrases = [p.strip() for p in phrases if p.strip()]
        if pq.intent == "general":
            pq.intent = "phrase"
        text = _PHRASE_RE.sub(" ", text)

    # Tokenize and filter stop words
    toks = [t for t in word_tokens(text) if t not in FILLER_WORDS and len(t) > 1]
    pq.tokens = toks
    pq.stems = list(dict.fromkeys(stem(t) for t in toks))

    if expand_synonyms:
        seen = set(pq.stems) | set(toks)
        for tok in toks:
            for syn in synonyms.expand(tok):
                for piece in syn.split():
                    s = stem(piece)
                    if s not in seen:
                        pq.synonyms.add(s)
                        seen.add(s)

    pq.fts_query = _build_fts(toks, pq.phrases)
    return pq
