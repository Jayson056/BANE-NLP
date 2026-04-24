"""
Tool Schema Validator (V2 Phase 2: Safety)
============================================
Enforces strict JSON Schema validation on every MCP tool call before
it reaches the OS execution layer. Prevents hallucinated tool names,
malformed arguments, and injection via extra fields.

Architecture:
    Engine Analyzer Loop → validate_tool_call() → execute / reject
"""

import re
from typing import Tuple, Optional, Set


# ── Schema Definition ─────────────────────────────────────────────────────────
# The canonical shape of a valid BNP tool call:
#   {"call_tool": "<registered_tool_name>", "args": { ... }}
#
# Extra keys like "thought", "reasoning", "description" are tolerated
# (the AI sometimes emits them) but NOT passed to the executor.
ALLOWED_EXTRA_KEYS = frozenset({
    "thought", "reasoning", "description", "mcp_type",
    "action", "tool", "details", "parameters",
})


def validate_tool_call(
    data: dict,
    registered_tools: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    """
    Validate a parsed tool-call dict against the BNP schema.

    Args:
        data:             The parsed JSON dict from the AI response.
        registered_tools: Set of currently registered MCP tool names.
                          If provided, the tool name must be in this set.

    Returns:
        (True, "")       if the call is valid.
        (False, reason)  if validation fails, with a human-readable reason.
    """
    # ── 1. Must have 'call_tool' ──────────────────────────────────────────
    if "call_tool" not in data:
        return False, "Missing required field 'call_tool'."

    tool_name = data["call_tool"]

    # ── 2. 'call_tool' must be a non-empty string ─────────────────────────
    if not isinstance(tool_name, str) or not tool_name.strip():
        return False, f"'call_tool' must be a non-empty string, got: {type(tool_name).__name__}"

    tool_name = tool_name.strip()

    # ── 3. Tool name format: category.function_name or simple_name ────────
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', tool_name):
        return False, f"Invalid tool name format: '{tool_name}'. Must be alphanumeric with dots/underscores."

    # ── 4. 'args' must be a dict (if present) ─────────────────────────────
    args = data.get("args")
    if args is not None and not isinstance(args, dict):
        return False, f"'args' must be a dict, got: {type(args).__name__}"

    # ── 5. Check against registered tool allowlist ────────────────────────
    if registered_tools is not None:
        if tool_name not in registered_tools:
            # Fuzzy match: suggest closest tool name
            suggestion = _fuzzy_match(tool_name, registered_tools)
            hint = f" Did you mean '{suggestion}'?" if suggestion else ""
            return False, f"Unknown tool: '{tool_name}'.{hint} Use meta_tools.list_tools to see available tools."

    # ── 6. Reject suspicious extra keys (not in allowed set) ──────────────
    extra_keys = set(data.keys()) - {"call_tool", "args"} - ALLOWED_EXTRA_KEYS
    if extra_keys:
        return False, f"Unexpected fields in tool call: {extra_keys}. Only 'call_tool' and 'args' are required."

    return True, ""


def sanitize_tool_call(data: dict) -> dict:
    """
    Return a clean, normalized copy of the tool call with only
    'call_tool' and 'args' keys.
    """
    return {
        "call_tool": data["call_tool"].strip(),
        "args": data.get("args") or {},
    }


def _fuzzy_match(name: str, candidates: Set[str], threshold: float = 0.6) -> Optional[str]:
    """
    Find the closest matching tool name using simple similarity.
    Returns None if no candidate exceeds the threshold.
    """
    best_score = 0.0
    best_match = None
    name_lower = name.lower()

    for candidate in candidates:
        c_lower = candidate.lower()
        # Simple substring check first
        if name_lower in c_lower or c_lower in name_lower:
            return candidate
        # Jaccard similarity on character bigrams
        name_bigrams = set(name_lower[i:i+2] for i in range(len(name_lower) - 1))
        cand_bigrams = set(c_lower[i:i+2] for i in range(len(c_lower) - 1))
        if not name_bigrams or not cand_bigrams:
            continue
        intersection = name_bigrams & cand_bigrams
        union = name_bigrams | cand_bigrams
        score = len(intersection) / len(union)
        if score > best_score:
            best_score = score
            best_match = candidate

    return best_match if best_score >= threshold else None
