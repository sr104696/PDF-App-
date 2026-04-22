"""
stemmer.py — Snowball English stemmer wrapper.

Replaces the three hand-written suffix rules from the v1 design
(sheet 7 rows 85-87) which had correctness bugs:
  "king" → "k",  "bed" → "b",  "is" → "i"

Snowball handles ~180 English suffix patterns correctly.
Falls back gracefully (returns the original word) when snowballstemmer
is not installed, so the search pipeline degrades rather than crashes.
"""

try:
    import snowballstemmer as _sb

    _stemmer = _sb.stemmer("english")
    _AVAILABLE = True
except ImportError:
    _stemmer = None
    _AVAILABLE = False


def stem_word(word: str) -> str:
    """Stem a single lowercase word. Returns original if stemmer unavailable."""
    if _AVAILABLE and word:
        return _stemmer.stemWord(word)
    return word


def stem_words(words: list[str]) -> list[str]:
    """Stem a list of lowercase words."""
    if not _AVAILABLE:
        return words
    return _stemmer.stemWords(words)


def is_available() -> bool:
    return _AVAILABLE
