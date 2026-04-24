# BANE-NLP AUTO-FIX: Message Chunking Utility
import logging

def chunk_text(text, limit=4000):
    """Splits text into chunks to prevent Telegram/Messenger truncation."""
    if not text: return []
    chunks = []
    raw_text = str(text)
    while len(raw_text) > limit:
        # Try to find a logical break point (newline) to maintain formatting
        idx = raw_text.rfind('\n', 0, limit)
        if idx == -1: 
            idx = limit
        chunks.append(raw_text[:idx].strip())
        raw_text = raw_text[idx:].strip()
    if raw_text: 
        chunks.append(raw_text)
    return chunks