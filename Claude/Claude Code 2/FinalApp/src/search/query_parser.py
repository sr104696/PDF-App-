"""Holistic query parser — T1 + T2 intent engine.

Steps:
  1. Detect intent (8 classes, multi-label).
  2. Decompose query into semantic atoms.
  3. Expand each atom through five circles:
       stems, direct_synonyms, concept_neighbors,
       corpus_cooccurrents (filled later by searcher),
       embedding_neighbors (filled later if model present).
  4. Build FTS5 MATCH expression from stems + direct + concepts.
  5. Detect quoted phrases for exact-match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Set, Tuple

from ..core.tokenizer import word_tokens
from ..utils.constants import FILLER_WORDS
from ..utils.synonyms import AtomExpansion, expand_atom
from .stemmer import stem, stem_all

# ── Regex helpers ────────────────────────────────────────────────────────────
_PHRASE_RE = re.compile(r'"([^"]{1,200})"')
_DEFINE_RE = re.compile(
    r"^(?:define|definition of|what is|what'?s|meaning of|explain)\s+(.+)$",
    re.IGNORECASE,
)
_FILLER_STRIP = re.compile(
    r"\b(find|search|show|get|give me|look for|tell me about|write|list|"
    r"quotes about|passages on|examples of|definition of|explain)\b",
    re.IGNORECASE,
)

# Intent signal patterns
_INTENT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("quote_seek",     re.compile(r"\b(quote|quotes|quoted|passage|passages|said|wrote|noted|"
                                  r"remarked|stated|exclaimed|aphorism|saying|words)\b", re.I)),
    ("emotional_theme",re.compile(r"\b(love|loss|grief|sorrow|joy|fear|hope|pain|anger|beauty|"
                                   r"longing|yearning|tenderness|ache|melancholy|wonder|"
                                   r"courage|despair|suffering|compassion|shame|guilt|"
                                   r"pride|regret|nostalgia|loneliness|longing|desire)\b", re.I)),
    ("definition",     re.compile(r"\b(define|definition|what is|what'?s|meaning|means|explain|"
                                   r"concept of|notion of)\b", re.I)),
    ("example_seek",   re.compile(r"\b(example|examples|instance|instances|case|cases|"
                                   r"such as|like|illustration|illustrate)\b", re.I)),
    ("comparison",     re.compile(r"\b(difference|differences|vs\.?|versus|compare|comparison|"
                                   r"contrast|distinguish|between)\b", re.I)),
    ("narrative",      re.compile(r"\b(story|stories|scene|moment|chapter|episode|event|"
                                   r"narrative|account|description|depict)\b", re.I)),
    ("person_seek",    re.compile(r"\b(who is|who was|biography|life of|about [A-Z][a-z]+)\b")),
]

# Structure type boosted per intent
INTENT_STRUCT_BOOST: Dict[str, List[str]] = {
    "quote_seek":      ["quote_block", "dialogue"],
    "definition":      ["heading_body", "exposition"],
    "example_seek":    ["list", "exposition"],
    "narrative":       ["dialogue", "exposition"],
    "emotional_theme": ["quote_block", "poetry", "dialogue"],
    "comparison":      ["exposition", "list"],
    "person_seek":     ["exposition", "heading_body"],
    "general":         [],
}


@dataclass
class ParsedQuery:
    raw: str
    intents: List[str] = field(default_factory=list)
    atoms: List[str] = field(default_factory=list)           # semantic atoms (lowercased)
    expansions: List[AtomExpansion] = field(default_factory=list)

    # Flat term sets for search (stemmed)
    stems: List[str] = field(default_factory=list)
    direct_stems: List[str] = field(default_factory=list)
    concept_stems: List[str] = field(default_factory=list)
    cooc_stems: List[str] = field(default_factory=list)      # filled by searcher at query time

    phrases: List[str] = field(default_factory=list)
    tokens: List[str] = field(default_factory=list)          # raw filtered tokens
    fts_query: str = ""
    boosted_structures: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.tokens or self.phrases)


# ── Public API ───────────────────────────────────────────────────────────────
def parse(raw: str) -> ParsedQuery:
    pq = ParsedQuery(raw=raw or "")
    if not raw or not raw.strip():
        return pq

    text = raw.strip()

    # 1. Extract quoted phrases
    phrases = _PHRASE_RE.findall(text)
    if phrases:
        pq.phrases = [p.strip() for p in phrases if p.strip()]
        text = _PHRASE_RE.sub(" ", text)

    # 2. Detect intents (multi-label)
    intents: List[str] = []
    for intent_name, pattern in _INTENT_PATTERNS:
        if pattern.search(raw):
            intents.append(intent_name)
    if not intents:
        intents = ["general"]
    pq.intents = intents

    # 3. Strip filler / intent-signal words to isolate content atoms
    text = _FILLER_STRIP.sub(" ", text)
    if _DEFINE_RE.match(text.strip()):
        m = _DEFINE_RE.match(text.strip())
        if m:
            text = m.group(1)

    # 4. Tokenize + filter stop words
    toks = [t for t in word_tokens(text) if t not in FILLER_WORDS and len(t) > 1]
    pq.tokens = toks

    # 5. Semantic atoms = unique content words (preserve order, dedup)
    seen: Set[str] = set()
    atoms: List[str] = []
    for t in toks:
        if t not in seen:
            seen.add(t)
            atoms.append(t)
    pq.atoms = atoms

    # 6. Expand each atom
    all_stems: List[str] = []
    all_direct: List[str] = []
    all_concepts: List[str] = []

    for atom in atoms:
        stemmed_atom = stem(atom)
        all_stems.append(stemmed_atom)
        exp = expand_atom(atom)
        pq.expansions.append(exp)
        # Stem all expansion terms
        for t in exp.direct:
            for word in t.split():
                s = stem(word)
                if s not in all_stems and s not in all_direct:
                    all_direct.append(s)
        for t in exp.concepts:
            for word in t.split():
                s = stem(word)
                if s not in all_stems and s not in all_direct and s not in all_concepts:
                    all_concepts.append(s)

    pq.stems = list(dict.fromkeys(all_stems))
    pq.direct_stems = list(dict.fromkeys(all_direct))
    pq.concept_stems = list(dict.fromkeys(all_concepts))

    # 7. Build FTS5 MATCH expression
    pq.fts_query = _build_fts(pq.tokens, pq.phrases, pq.direct_stems, pq.concept_stems)

    # 8. Collect boosted structure types from all detected intents
    boosted: List[str] = []
    for intent in intents:
        for s in INTENT_STRUCT_BOOST.get(intent, []):
            if s not in boosted:
                boosted.append(s)
    pq.boosted_structures = boosted

    return pq


def _escape_fts(term: str) -> str:
    """Escape a term for FTS5 MATCH. Use quoted form to handle punctuation."""
    safe = term.replace('"', '""').strip()
    return f'"{safe}"*' if safe else ""


def _build_fts(
    tokens: List[str],
    phrases: List[str],
    direct_stems: List[str],
    concept_stems: List[str],
) -> str:
    parts: List[str] = []

    # Exact phrases (highest priority)
    for ph in phrases:
        safe = ph.replace('"', '""')
        parts.append(f'"{safe}"')

    # Stems + direct synonyms combined into main OR clause
    all_primary = list(dict.fromkeys(
        [_escape_fts(t) for t in tokens if t.isalpha()] +
        [_escape_fts(t) for t in direct_stems if t]
    ))
    all_primary = [t for t in all_primary if t]

    # Concept terms as secondary OR clause
    all_concept = list(dict.fromkeys(
        [_escape_fts(t) for t in concept_stems if t]
    ))
    all_concept = [t for t in all_concept if t]

    if all_primary:
        parts.append("(" + " OR ".join(all_primary) + ")")
    if all_concept:
        parts.append("(" + " OR ".join(all_concept) + ")")

    return " OR ".join(p for p in parts if p)
