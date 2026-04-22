"""
query_parser.py -- Parse and normalise a user search query.

Steps (sheet 21 search pipeline, step 1 & 2):
  1. Extract quoted phrases (FTS5 phrase-match).
  2. Remove filler / stop words from remaining tokens.
  3. Detect intent: quote-search, definition, comparison, example.
  4. Stem remaining terms with Snowball.
  5. Expand: add synonym forms as a boost set (additive, not primary).
  6. Build the FTS5 match expression.
"""
from __future__ import annotations

import re

from src.search.stemmer import stem_word, stem_words
from src.utils.synonyms import expand

# -- Stop words ----------------------------------------------------------------
STOP_WORDS: frozenset = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "a", "an", "the", "and", "but", "if", "or", "because", "as",
    "until", "while", "of", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "s", "t",
    "can", "will", "just", "don", "should", "now",
    "d", "ll", "m", "o", "re", "ve", "y",
    "ain", "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven",
    "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn",
    "wasn", "weren", "won", "wouldn",
})

# -- Intent detection ----------------------------------------------------------
_INTENT_PATTERNS = {
    "quote":      re.compile(r"\b(quot\w*|said|says|stat\w+|phrase|passage)\b", re.I),
    "definition": re.compile(r"\b(defin\w+|what\s+is|meaning\s+of|explain\w*)\b", re.I),
    "comparison": re.compile(r"\b(compar\w*|versus|vs\.?|differ\w*|similar\w*)\b", re.I),
    "example":    re.compile(r"\b(example\w*|instance|illustrat\w*)\b", re.I),
}

_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
_PHRASE_RE = re.compile(r'"([^"]+)"')


class ParsedQuery:
    """Result of query parsing."""

    def __init__(self, raw, phrases, terms, stemmed, synonyms, intent):
        self.raw = raw
        self.phrases = phrases
        self.terms = terms
        self.stemmed = stemmed
        self.synonyms = synonyms
        self.intent = intent

    def is_empty(self):
        return not self.phrases and not self.terms

    def fts_expression(self):
        """
        Build an FTS5 MATCH expression.
        Quoted phrases become FTS5 phrase literals.
        Remaining terms get a prefix wildcard (*) for partial matching.
        Terms ORed together; phrases ANDed with terms.
        """
        parts = []

        for phrase in self.phrases:
            safe = phrase.replace('"', '""')
            parts.append('"' + safe + '"')

        all_terms = []
        seen = set()
        for t in list(self.stemmed) + list(self.terms) + list(self.synonyms):
            if t and t not in seen:
                seen.add(t)
                all_terms.append(t)

        if all_terms:
            term_expr = " OR ".join(t + "*" for t in all_terms)
            parts.append("(" + term_expr + ")")

        return " AND ".join(parts)


def parse(query):
    """Parse a user query string into a ParsedQuery."""
    if not query or not query.strip():
        return ParsedQuery("", [], [], [], [], "general")

    raw = query.strip()

    # 1. Extract quoted phrases
    phrases = [m.lower() for m in _PHRASE_RE.findall(raw) if m.strip()]
    remaining = _PHRASE_RE.sub("", raw)

    # 2. Tokenise + stop-filter
    words = [w.lower() for w in _WORD_RE.findall(remaining)]
    terms = [w for w in words if w not in STOP_WORDS and len(w) > 1]

    # 3. Detect intent
    intent = "general"
    for name, pat in _INTENT_PATTERNS.items():
        if pat.search(raw):
            intent = name
            break

    # 4. Stem
    stemmed = list(dict.fromkeys(stem_words(terms)))

    # 5. Synonym expansion (boost set only)
    syn_set = []
    seen_syns = set(stemmed) | set(terms)
    for t in terms:
        for s in expand(t):
            s_lower = s.lower()
            if s_lower not in seen_syns:
                syn_set.append(s_lower)
                seen_syns.add(s_lower)

    return ParsedQuery(
        raw=raw,
        phrases=phrases,
        terms=terms,
        stemmed=stemmed,
        synonyms=syn_set,
        intent=intent,
    )
