"""
BNP Context Builder
====================
Dynamically builds AI prompt context by combining:
  1. Static AI_SKILLS.md rules (identity, styling, mission)
  2. Dynamic conversation history from the database
  3. Optional knowledge memory

Architecture:
    AI_SKILLS.md (static) + Database (dynamic) → Enriched Prompt → Gemini/NotebookLM
"""

from typing import Optional, List, Dict, Any

from core.database import get_recent_messages, search_memory


def build_context(conversation_id: str, max_history: int = 10) -> str:
    """
    Build a dynamic context string from the database for prompt injection.
    
    This is injected INTO the prompt alongside the static AI_SKILLS.md attachment,
    giving the AI awareness of the ongoing conversation without modifying the file.
    
    Args:
        conversation_id: The active conversation ID.
        max_history: Maximum number of recent messages to include.
    
    Returns:
        A formatted context string ready for prompt injection.
    """
    messages = get_recent_messages(conversation_id, limit=max_history)

    if not messages:
        return ""

    # Build conversation replay
    lines = []
    import re
    # Patterns to remove technical BN/NLP internal headers/footers
    scrub_patterns = [
        r'\[SYSTEM: MISSION\].*?\|',
        r'\[IDENTITY & PERSONA\].*?\]',
        r'\[MANDATORY OUTPUT CONSTRAINTS\].*?\]',
        r'\[EXECUTION COMMAND\].*?\]',
        r'\[BANE NLP — OPERATIONAL DIRECTIVE\].*?\[END DIRECTIVE\]',
        r'\[CONVERSATION CONTEXT.*?\[END CONTEXT\]',
        r'\[IDENTITY: BANE NLP.*?\]',
        r'USER: Jayson \| INPUT:',
        r'\[MANDATORY_SYNTAX.*?\]',
        r'\[CRITICAL INSTRUCTION:.*?\]',
    ]
    
    for msg in messages:
        sender = msg.get("sender_type", "UNKNOWN")
        content = msg.get("message_content", "")
        
        # 🧪 Surgical Scrub: Remove technical rules/headers from context history
        for pattern in scrub_patterns:
            content = re.sub(pattern, "", content, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # Remove extra whitespace left by scrubbing
        content = re.sub(r'\n{3,}', '\n\n', content).strip()
        
        if not content: continue
        
        # Truncate very long messages to keep context window lean
        if len(content) > 500:
            content = content[:500] + "..."
            
        label = "User" if sender == "USER" else "BANE" if sender == "AI" else "System"
        lines.append(f"{label}: {content}")

    raw_history = "\n".join(lines)

    # V2 Phase 4: Compact context if it exceeds token limits
    from pipeline.context_compactor import compact_context
    compacted_history, was_compacted = compact_context(raw_history)
    
    return compacted_history


def build_memory_context(query: str, max_results: int = 3) -> str:
    """
    Search knowledge memory for relevant context to inject.
    
    Args:
        query: The user's current message (used as search keyword).
        max_results: Max memory entries to retrieve.
    
    Returns:
        A formatted memory context string, or empty string if nothing found.
    """
    # Extract keywords (simple: first 3 significant words)
    words = [w for w in query.split() if len(w) > 3]
    if not words:
        return ""

    results: List[Dict[str, Any]] = []
    for word in words[:3]:
        hits = search_memory(word, limit=max_results)
        for h in hits:
            if h not in results:
                results.append(h)

    if not results:
        return ""

    lines = ["[KNOWLEDGE MEMORY — Relevant stored intelligence]"]
    for mem in results[:max_results]:
        lines.append(f"• {mem['topic']}: {mem['summary']}")
    lines.append("[END MEMORY]")

    return "\n".join(lines)
