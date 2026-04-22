"""
Query Parser Module - Fixed version with correct stemming logic.
"""
import re
from typing import List, Dict, Set

from stemmer import stem_word
from synonyms import load_synonyms

# A simple list of english stop words to filter out
STOP_WORDS = {
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', "you're", "you've", "you'll", "you'd",
    'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', "she's", 'her', 'hers',
    'herself', 'it', "it's", 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which',
    'who', 'whom', 'this', 'that', "that'll", 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if',
    'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between',
    'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out',
    'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why',
    'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', "don't", 'should',
    "should've", 'now', 'd', 'll', 'm', 'o', 're', 've', 'y', 'ain', 'aren', "aren't", 'couldn', "couldn't",
    'didn', "didn't", 'doesn', "doesn't", 'hadn', "hadn't", 'hasn', "hasn't", 'haven', "haven't", 'isn', "isn't",
    'ma', 'mightn', "mightn't", 'mustn', "mustn't", 'needn', "needn't", 'shan', "shan't", 'shouldn', "shouldn't",
    'wasn', "wasn't", 'weren', "weren't", 'won', "won't", 'wouldn', "wouldn't"
}


def parse_query(query_string: str) -> Dict:
    """
    Parses a search query.
    Extracts quoted strings for exact matches, removes stopwords for the rest,
    applies stemming, and optional synonym expansion.
    
    Args:
        query_string: The raw search query string.
        
    Returns:
        Dictionary containing:
        - exact_phrases: List of exact phrase queries
        - terms: List of filtered terms (stopwords removed)
        - stemmed_terms: List of stemmed terms
        - expanded_terms: List of synonym-expanded terms
    """
    result: Dict[str, List] = {
        "exact_phrases": [],
        "terms": [],
        "stemmed_terms": [],
        "expanded_terms": []
    }
    
    # 1. Extract exact phrases
    exact_matches = re.findall(r'"([^"]*)"', query_string)
    result["exact_phrases"] = [m.lower() for m in exact_matches if m.strip()]
    
    # Remove exact phrases from main query string to process remaining words
    remaining_query = re.sub(r'"([^"]*)"', '', query_string)
    
    # 2. Extract remaining words, remove stop words
    words = re.findall(r'\b\w+\b', remaining_query.lower())
    filtered_words = [w for w in words if w not in STOP_WORDS]
    result["terms"] = filtered_words
    
    # 3. Stemming - FIXED: Use stem_word for individual words
    result["stemmed_terms"] = [stem_word(w) for w in filtered_words]
    
    # 4. Synonym Expansion (Optional boost)
    synonyms_dict = load_synonyms()
    expanded_set: Set[str] = set()
    
    for word in filtered_words:
        if word in synonyms_dict:
            # Add synonyms as expanded terms
            for syn in synonyms_dict[word]:
                expanded_set.add(syn.lower())
    
    result["expanded_terms"] = list(expanded_set)
    
    return result
