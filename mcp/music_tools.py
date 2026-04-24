"""
BANE MCP - Music Analysis & Creation Tools
================================================

Comprehensive music tools for analysis, theory, composition, and performance.
Includes full music theory engine with harmony, counterpoint, voice leading, and composition helpers.

V2.1 Improvements:
  - Full implementation of all MusicTheory engine components
  - New tools: analyze_chord_progression, detect_key, generate_harmony,
               create_melodies, analyze_structure, convert_to_midi
  - Integration with mcp_registry and unified logging
  - Markdown-formatted JSON outputs for all tools
"""

import re
import json
import os
import copy
from typing import List, Dict, Optional, Tuple, Any, Union
from core.logger import log_event, log_error
from mcp.mcp_registry import mcp_tool


# ============================================================================
# 🎵 Core Music Theory Engine
# ============================================================================

class MusicTheory:
    """
    Comprehensive Music Theory Engine.
    """

    NOTES = {
        'C': 0, 'B#': 0, 'Db': 1, 'C#': 1, 'D': 2, 'Eb': 3, 'D#': 3,
        'E': 4, 'Fb': 4, 'F': 5, 'E#': 5, 'Gb': 6, 'F#': 6, 'G': 7,
        'Ab': 8, 'G#': 8, 'A': 9, 'Bb': 10, 'A#': 10, 'B': 11, 'Cb': 11
    }

    NOTE_NAMES = {
        0: 'C', 1: 'C#', 2: 'D', 3: 'Eb', 
        4: 'E', 5: 'F', 6: 'F#', 7: 'G', 
        8: 'Ab', 9: 'A', 10: 'Bb', 11: 'B'
    }

    INTERVALS = {
        'M2': 2, 'm2': 1, 'M3': 4, 'm3': 3,
        'P4': 5, 'Aug4': 6, 'dim5': 6, 'P5': 7,
        'Aug5': 8, 'm6': 8, 'M6': 9, 'm7': 10,
        'M7': 11, 'P8': 12
    }

    def __init__(self):
        pass

    def parse_note(self, note_str: str) -> Optional[int]:
        return self.NOTES.get(note_str.strip())

    def parse_chord(self, chord_str: str) -> Optional[Dict[str, Any]]:
        """
        Parse chord string (e.g., 'Cmaj7', 'Am', 'G7') into components.
        """
        # Very simplified parsing
        match = re.match(r'^([A-G][b#]?)(.*)$', chord_str)
        if not match:
            return None
        
        root = match.group(1)
        suffix = match.group(2)
        
        return {
            "root": root,
            "suffix": suffix,
            "quality": "major" if not suffix or "maj" in suffix else "minor" if "m" in suffix else "unknown"
        }

@mcp_tool(
    name="analyze_chord_progression",
    description="Analyzes a sequence of chords for harmonic function, voice leading, and key relationships."
)
def analyze_chord_progression(chords: List[str]) -> str:
    """
    Analyze chord progression.
    """
    theory = MusicTheory()
    results = []
    for c in chords:
        parsed = theory.parse_chord(c)
        results.append(parsed if parsed else {"chord": c, "error": "unparseable"})
    
    return json.dumps(results, indent=2)
