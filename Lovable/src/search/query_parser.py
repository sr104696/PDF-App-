"""Query parser (sheet 21).

Responsibilities:
* Strip filler words (constants.FILLER_WORDS).
* Detect intent flags: phrase queries ("..."), definition queries (define X / what is X).
* Produce both the original tokens and stemmed tokens.
* Optionally produce a synonym-expanded token set for soft boosting.
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


@dataclass
class ParsedQuery:
    raw: str
    tokens: List[str] = field(default_factory=list)         # filtered, lowercase
    stems: List[str] = field(default_factory=list)
    phrases: List[str] = field(default_factory=list)        # exact phrases
    synonyms: Set[str] = field(default_factory=set)         # stems
    intent: str = "general"                                  # general | definition | phrase
    fts_query: str = ""                                      # SQLite FTS5 MATCH expression

    def is_empty(self) -> bool:
        return not (self.tokens or self.phrases)


def _build_fts(tokens: List[str], phrases: List[str]) -> str:
    """Build an FTS5 MATCH expression. Phrases quoted, tokens OR-joined with prefix."""
    parts: List[str] = []
    for ph in phrases:
        safe = ph.replace('"', '""')
        parts.append(f'"{safe}"')
    if tokens:
        # Prefix match (token*) lets FTS catch "running" when user types "run".
        parts.append(" OR ".join(f'{t}*' for t in tokens if t.isalnum()))
    return " AND ".join(p for p in parts if p)


def parse(raw: str, expand_synonyms: bool = True) -> ParsedQuery:
    pq = ParsedQuery(raw=raw or "")
    if not raw or not raw.strip():
        return pq
    text = raw.strip()

    m = _DEFINE_RE.match(text)
    if m:
        pq.intent = "definition"
        text = m.group(1)

    phrases = _PHRASE_RE.findall(text)
    if phrases:
        pq.phrases = [p.strip() for p in phrases if p.strip()]
        pq.intent = "phrase" if pq.intent == "general" else pq.intent
        text = _PHRASE_RE.sub(" ", text)

    toks = [t for t in word_tokens(text) if t not in FILLER_WORDS and len(t) > 1]
    pq.tokens = toks
    pq.stems = [stem(t) for t in toks]

    if expand_synonyms:
        for tok in toks:
            for syn in synonyms.expand(tok):
                for piece in syn.split():
                    pq.synonyms.add(stem(piece))
        # Don't let synonyms duplicate the primary stems.
        pq.synonyms.difference_update(pq.stems)

    pq.fts_query = _build_fts(toks, pq.phrases)
    return pq
