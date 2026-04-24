"""
BANE V3 — MCP Voice Tools
Handles switching between text and voice processing modes.
"""

import os
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event

@mcp_custom_tool(name="voice_tools.enable_voice_mode", description="Enable voice mode to initialize audio capture and speech recognition. Call this when the user says /voice. Args: {}")
def enable_voice_mode() -> str:
    """
    Initializes the voice pipeline. 
    Note: The actual voice state is managed by the platform bots, 
    but this tool provides the AI-visible status update.
    """
    log_event("MCP", "Voice mode enabled via tool call.")
    # Return the EXACT string required by MANDATORY_RULES.txt
    return "Voice mode enabled. Listening for audio."

@mcp_custom_tool(name="/voice", description="Shorthand for voice mode initialization. Args: {}")
def voice_shorthand() -> str:
    """Alias for enable_voice_mode to catch direct command patterns."""
    return enable_voice_mode()
