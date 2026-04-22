"""
Stemmer Module - Unchanged from original.
"""
try:
    import snowballstemmer
    _stemmer = snowballstemmer.stemmer('english')
except ImportError:
    _stemmer = None


def stem_word(word: str) -> str:
    """
    Stem a single word using Snowball stemmer, fallback to original if unavailable.
    
    Args:
        word: The word to stem.
        
    Returns:
        The stemmed word, or the original word if stemmer is unavailable.
    """
    if _stemmer:
        return _stemmer.stemWord(word)
    return word


def stem_text(text: str) -> list:
    """
    Stem a list of words.
    
    Args:
        text: Text to stem (will be tokenized first).
        
    Returns:
        List of stemmed words.
    """
    from src.core.tokenizer import tokenize
    words = tokenize(text)
    return [stem_word(w) for w in words]
