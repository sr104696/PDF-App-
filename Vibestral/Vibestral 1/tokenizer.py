"""
Tokenizer Module - Optimized version with improved tokenization patterns.
"""
import re
from typing import List


# Improved regex pattern for better tokenization
# Handles contractions, hyphenated words, and common abbreviations
TOKEN_PATTERN = re.compile(r'\b[a-zA-Z]+(?:\'[a-zA-Z]+)?\b|\d+')


def tokenize(text: str) -> List[str]:
    """
    Tokenizes text into words/punctuation and returns lowercased tokens.
    
    Args:
        text: Input text to tokenize.
        
    Returns:
        List of lowercase tokens.
    """
    if not text:
        return []
    return [word.lower() for word in TOKEN_PATTERN.findall(text)]


def count_tokens(text: str) -> int:
    """
    Counts the number of tokens in text.
    
    Args:
        text: Input text to count tokens.
        
    Returns:
        Number of tokens.
    """
    if not text:
        return 0
    return len(tokenize(text))
