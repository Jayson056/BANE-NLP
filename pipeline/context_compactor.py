"""
Context Compactor (V2 Phase 4: Efficiency)
============================================
Implements tiered state management with automatic context compaction.

When conversational history approaches 70% of the token limit, this module
strips verbose [TOOL RESULT] blocks and compresses older exchanges into
high-fidelity summaries while keeping the most recent exchanges intact.

Architecture:
    context_builder.py → build raw history
        ↓
    context_compactor.py → compact_context() if tokens exceed threshold
        ↓
    Compacted context injected into PipelineContext.dynamic_context
"""

import re
from typing import Tuple

from core.logger import log_event


# ── Configuration ─────────────────────────────────────────────────────────────
TOKEN_LIMIT = 8000                # Approximate token budget for context window
COMPACTION_THRESHOLD = 0.7        # Trigger compaction at 70% of limit
RECENT_EXCHANGES_TO_KEEP = 3     # Always keep the N most recent exchanges intact
TOOL_RESULT_MAX_CHARS = 150      # Truncated tool result summary length


def estimate_tokens(text: str) -> int:
    """
    Fast token estimation using the ~4 chars/token heuristic.
    More accurate than word count for mixed code/text content.
    """
    if not text:
        return 0
    return len(text) // 4


def compact_context(conversation_history: str) -> Tuple[str, bool]:
    """
    Conditionally compact conversation history to fit within token limits.

    Strategy:
        1. Check if history exceeds COMPACTION_THRESHOLD.
        2. If so, split into exchanges (USER/AI pairs).
        3. Keep the most recent RECENT_EXCHANGES_TO_KEEP intact.
        4. For older exchanges:
           a. Strip verbose [TOOL RESULT] blocks to one-liner summaries.
           b. Collapse long AI responses to first 2 sentences.
        5. Return compacted string.

    Args:
        conversation_history: The raw conversation history string.

    Returns:
        (compacted_text, was_compacted) tuple.
    """
    if not conversation_history:
        return conversation_history, False

    token_est = estimate_tokens(conversation_history)
    threshold = int(TOKEN_LIMIT * COMPACTION_THRESHOLD)

    if token_est <= threshold:
        return conversation_history, False

    log_event("COMPACTOR", (
        f"Context compaction triggered: ~{token_est} tokens "
        f"exceeds threshold of {threshold} ({COMPACTION_THRESHOLD*100:.0f}% of {TOKEN_LIMIT})"
    ))

    # ── Split history into individual exchanges ───────────────────────────
    exchanges = _split_exchanges(conversation_history)

    if len(exchanges) <= RECENT_EXCHANGES_TO_KEEP:
        # Not enough exchanges to compact, just strip tool results
        compacted = _strip_tool_results(conversation_history)
        log_event("COMPACTOR", f"Compacted via tool-result stripping: {token_est} → ~{estimate_tokens(compacted)} tokens")
        return compacted, True

    # ── Keep recent exchanges intact ──────────────────────────────────────
    recent = exchanges[-RECENT_EXCHANGES_TO_KEEP:]
    older = exchanges[:-RECENT_EXCHANGES_TO_KEEP]

    # ── Compact older exchanges ───────────────────────────────────────────
    compacted_older = []
    for exchange in older:
        compacted_exchange = _compact_single_exchange(exchange)
        compacted_older.append(compacted_exchange)

    # ── Reassemble ────────────────────────────────────────────────────────
    compacted_parts = []
    if compacted_older:
        compacted_parts.append("[COMPACTED HISTORY]")
        compacted_parts.extend(compacted_older)
        compacted_parts.append("[END COMPACTED HISTORY]")
        compacted_parts.append("")  # Blank line separator

    compacted_parts.extend(recent)

    compacted = "\n".join(compacted_parts)
    new_tokens = estimate_tokens(compacted)

    log_event("COMPACTOR", (
        f"Compaction complete: {token_est} → ~{new_tokens} tokens "
        f"({len(older)} older exchanges compacted, {len(recent)} kept intact)"
    ))

    return compacted, True


def _split_exchanges(history: str) -> list:
    """
    Split conversation history into individual exchanges.
    Each exchange starts with a role marker like [USER], [AI], USER:, AI:, etc.
    """
    # Split on common role markers
    parts = re.split(r'(?=\[(?:USER|AI|SYSTEM)\]|(?:USER|AI|SYSTEM):)', history)
    exchanges = [p.strip() for p in parts if p.strip()]
    return exchanges


def _strip_tool_results(text: str) -> str:
    """
    Replace verbose [TOOL RESULT] blocks with compact one-liner summaries.
    """
    def _summarize_tool_result(match):
        content = match.group(1).strip()
        # Extract just the first meaningful line
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if lines:
            summary = lines[0][:TOOL_RESULT_MAX_CHARS]
            if len(lines) > 1 or len(lines[0]) > TOOL_RESULT_MAX_CHARS:
                summary += f"... ({len(content)} chars total)"
            return f"[TOOL RESULT: {summary}]"
        return "[TOOL RESULT: empty]"

    # Match [TOOL RESULT: ...content... [END TOOL RESULT]
    compacted = re.sub(
        r'\[TOOL RESULT:?\s*\](.*?)\[END TOOL RESULT\]',
        _summarize_tool_result,
        text,
        flags=re.DOTALL
    )

    # Also match inline tool results without END marker
    compacted = re.sub(
        r'\[TOOL RESULT\]\s*(.*?)(?=\n\[(?:USER|AI)|$)',
        _summarize_tool_result,
        compacted,
        flags=re.DOTALL
    )

    return compacted


def _compact_single_exchange(exchange: str) -> str:
    """
    Compact a single exchange:
      - Strip tool results to summaries
      - Truncate very long AI responses to first 2 sentences
    """
    # First strip tool results
    compacted = _strip_tool_results(exchange)

    # If this is an AI response and it's still very long, truncate
    if compacted.startswith("[AI]") or compacted.startswith("AI:"):
        lines = compacted.split('\n')
        header = lines[0]
        body = '\n'.join(lines[1:]).strip()

        if len(body) > 500:
            # Keep first 2 sentences
            sentences = re.split(r'(?<=[.!?])\s+', body)
            truncated = '. '.join(sentences[:2])
            if not truncated.endswith('.'):
                truncated += '.'
            compacted = f"{header}\n{truncated} [... response truncated for context efficiency]"

    return compacted
