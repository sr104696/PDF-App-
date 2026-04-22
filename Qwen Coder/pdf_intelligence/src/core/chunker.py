"""
Chunker Module - Optimized version with accurate character position tracking.
"""
import re
from typing import List, Dict

from src.core.tokenizer import count_tokens


def chunk_text(text: str, max_tokens: int = 512) -> List[Dict]:
    """
    Chunks text into smaller pieces.
    Attempts to split by paragraphs, then sentences if necessary.
    
    Args:
        text: Input text to chunk.
        max_tokens: Maximum number of tokens per chunk.
        
    Returns:
        A list of dicts: [{'text': '...', 'start_char': 0, 'end_char': 100, 'token_count': 20}, ...]
    """
    if not text:
        return []
    
    chunks = []
    
    # Split by double newline (paragraphs)
    paragraphs = re.split(r'\n\s*\n', text)
    
    current_chunk = ""
    current_start = 0
    current_tokens = 0
    
    # Track the actual position in the original text
    text_pos = 0
    
    for para_idx, para in enumerate(paragraphs):
        # Find the actual position of this paragraph in the original text
        para_pos = text.find(para, text_pos)
        if para_pos == -1:
            para_pos = text_pos
        
        para_tokens = count_tokens(para)
        
        # If paragraph is too big, split by sentences
        if para_tokens > max_tokens:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            sent_pos = 0
            
            for sent in sentences:
                # Find sentence position within paragraph
                sent_in_para = para.find(sent, sent_pos)
                if sent_in_para == -1:
                    sent_in_para = sent_pos
                
                abs_sent_pos = para_pos + sent_in_para
                sent_tokens = count_tokens(sent)
                
                if current_tokens + sent_tokens > max_tokens and current_chunk:
                    # Save current chunk
                    end_char = current_start + len(current_chunk)
                    chunks.append({
                        "text": current_chunk.strip(),
                        "start_char": current_start,
                        "end_char": end_char,
                        "token_count": current_tokens
                    })
                    current_chunk = sent + " "
                    current_start = abs_sent_pos
                    current_tokens = sent_tokens
                else:
                    current_chunk += sent + " "
                    current_tokens += sent_tokens
                
                sent_pos = sent_in_para + len(sent)
        else:
            if current_tokens + para_tokens > max_tokens and current_chunk:
                # Save current chunk
                end_char = current_start + len(current_chunk)
                chunks.append({
                    "text": current_chunk.strip(),
                    "start_char": current_start,
                    "end_char": end_char,
                    "token_count": current_tokens
                })
                current_chunk = para + "\n\n"
                current_start = para_pos
                current_tokens = para_tokens
            else:
                current_chunk += para + "\n\n"
                current_tokens += para_tokens
        
        text_pos = para_pos + len(para)
    
    # Don't forget the last chunk
    if current_chunk.strip():
        end_char = current_start + len(current_chunk)
        chunks.append({
            "text": current_chunk.strip(),
            "start_char": current_start,
            "end_char": end_char,
            "token_count": current_tokens
        })
    
    return chunks
