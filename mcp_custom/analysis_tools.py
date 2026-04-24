"""
BANE MCP - Analysis Tools
============================
Advanced analysis tools for research, synthesis, and complex data tasks.

Includes:
  - Text compression & summarization (multi-level)
  - Academic paper analysis (PDF, email, arXiv integration)
  - Multi-source content fusion (synthesis)
  - Academic concept extraction (ontology-based)
  - Academic concept verification (cross-reference)
  - Literature review assistance
  - Trend analysis & gap detection
  - Trend analysis & gap detection
"""

import re
import json
from typing import List, Dict, Optional, Tuple, Any

from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event, log_error


# ── Standard NLP Tools ───────────────────────────────────────────────────────

@mcp_custom_tool(
    name="compress_text",
    description="Compresses text by removing filler, reducing redundancy, and standardizing phrasing without losing meaning."
)
def compress_text(text: str, granularity: str = "medium", preserve_details: bool = True) -> str:
    """
    Compress text by removing filler, reducing redundancy, and standardizing phrasing.
    
    Args:
        text: The text to compress
        granularity: Level of compression ('medium', 'tight', 'minimal')
        preserve_details: Whether to keep minor details (default: True)
        
    Returns:
        Compressed text
    """
    log_event("MCP_ANALYSIS", f"Compressing text (granularity: {granularity}, preserve_details: {preserve_details})")
    
    # Basic compression strategy
    lines = text.strip().split('\n')
    compressed = []
    
    for line in lines:
        # Remove excessive whitespace
        line = re.sub(r'\s+', ' ', line).strip()
        
        # Skip empty lines
        if not line:
            continue
            
        # Skip filler phrases (can be enhanced)
        if re.match(r'^(well|uh|you see|actually)', line, re.IGNORECASE):
            continue
            
        compressed.append(line)
    
    return ' '.join(compressed)


@mcp_custom_tool(
    name="expand_abbreviations",
    description="Expands abbreviations and acronyms in text to full forms where contextually appropriate."
)
def expand_abbreviations(text: str, context: Optional[str] = None) -> str:
    """
    Expand abbreviations and acronyms.
    
    Args:
        text: Text containing abbreviations
        context: Academic subject context for better expansion
        
    Returns:
        Text with expanded abbreviations
    """
    log_event("MCP_ANALYSIS", f"Expanding abbreviations (context: {context or 'general'})")
    
    # Simplified expansion logic
    expansion_map = {
        "AI": "Artificial Intelligence",
        "NLP": "Natural Language Processing",
        "HTML": "HyperText Markup Language",
        "CSS": "Cascading Style Sheets",
        "JS": "JavaScript",
        "API": "Application Programming Interface",
    }
    
    if context:
        if "quantum" in context.lower():
            expansion_map["QM"] = "Quantum Mechanics"
            expansion_map["EPR"] = "Einstein-Podolsky-Rosen (paradox)"
        if "machine learning" in context.lower():
            expansion_map["ML"] = "Machine Learning"
            expansion_map["NN"] = "Neural Network"
    
    expanded_text = text
    for abbr, full in expansion_map.items():
        pattern = r'\b' + re.escape(abbr) + r'\b'
        expanded_text = re.sub(pattern, full, expanded_text, flags=re.IGNORECASE)
    
    return expanded_text


# ── Multi-Level Summarization ──────────────────────────────────────────────

@mcp_custom_tool(
    name="summarize_to_points",
    description="Summarizes text into a structured bulleted list of key points."
)
def summarize_to_points(text: str, points_count: int = 5) -> str:
    """
    Summarize text into a structured bulleted list.
    
    Args:
        text: Text to summarize
        points_count: Number of points to generate
        
    Returns:
        Bulleted summary
    """
    log_event("MCP_ANALYSIS", f"Summarizing to {points_count} points")
    
    lines = [l for l in text.strip().split('\n') if l.strip()]
    key_sentences = lines[:points_count]
    
    summary = f"Summary ({len(key_sentences)} key points):\n"
    for i, sentence in enumerate(key_sentences, 1):
        summary += f"  {i}. {sentence.strip()}\n"
    
    return summary


@mcp_custom_tool(
    name="generate_summary_levels",
    description="Generates summaries at multiple abstraction levels: detailed, medium, and one-sentence."
)
def generate_summary_levels(text: str, target_length: str = "medium") -> str:
    """
    Generate summaries at multiple levels: detailed, medium, and one-sentence.
    
    Args:
        text: Text to summarize
        target_length: Target level of detail
        
    Returns:
        Multi-level summary
    """
    log_event("MCP_ANALYSIS", f"Generating summaries at {target_length} level")
    
    lines = [l for l in text.strip().split('\n') if l.strip()]
    
    one_sentence = lines[0] if lines else "No content."
    medium_summary = "\n".join(lines[:5])
    detailed_summary = "\n".join(lines[:15])
    
    if target_length == "short":
        return f"ONE-SENTENCE SUMMARY:\n{one_sentence}"
    elif target_length == "medium":
        return f"MEDIUM SUMMARY:\n{medium_summary}"
    else:
        return f"DETAILED SUMMARY:\n{detailed_summary}"
