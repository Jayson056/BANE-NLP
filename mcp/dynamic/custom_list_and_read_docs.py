from mcp.mcp_registry import mcp_tool

import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("BANE_Custom_Tools")

@mcp.tool()
def list_and_read_docs(directory: str) -> str:
    """Reads all .md and .txt files from a directory and returns a single formatted string."""
    if not os.path.exists(directory):
        return f"Error: Directory {directory} not found."
    
    output = []
    for filename in os.listdir(directory):
        if filename.endswith(('.md', '.txt')):
            file_path = os.path.join(directory, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    output.append(f"--- FILE: {filename} ---\n{content}\n")
            except Exception as e:
                output.append(f"--- FILE: {filename} (ERROR) ---\nCould not read: {str(e)}\n")
    
    return "\n".join(output) if output else "No .md or .txt files found."