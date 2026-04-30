import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event

@mcp_custom_tool(
    name="system.view_file",
    description="Surgically view the contents of a file without outputting the whole file. Use this instead of generic read_file. Specify start_line and end_line to prevent crashing the extension with massive 1600+ line outputs. Args: {'absolute_path': 'C:/path/to/file.py', 'start_line': 1, 'end_line': 150}"
)
def view_file(absolute_path: str, start_line: int = None, end_line: int = None) -> str:
    """
    Reads a specific line range from a file to avoid overwhelming the context window.
    """
    if not os.path.exists(absolute_path):
        return f"❌ Error: File not found: {absolute_path}"
    
    try:
        with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        
        if start_line is None:
            start_line = 1
        if end_line is None:
            end_line = total_lines
            
        # Prevent massive dumps if they forget boundaries
        if (end_line - start_line) > 800:
            return f"❌ Error: Requested {end_line - start_line} lines. For stability in Telegram/Messenger, please request 800 lines or less at a time using start_line and end_line."

        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, end_line)
        
        sliced = lines[start_idx:end_idx]
        
        output = f"File: {absolute_path} (Lines {start_idx+1} to {end_idx} of {total_lines})\n"
        output += "-" * 50 + "\n"
        for i, line in enumerate(sliced, start=start_idx+1):
            output += f"{i:4d}: {line}"
        output += "\n" + "-" * 50
        
        log_event("MCP", f"Viewed file {absolute_path} (lines {start_idx+1}-{end_idx})")
        return output
    except Exception as e:
        return f"❌ Error reading file: {e}"
