import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool

import ast
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
# from mcp_custom import mcp_custom_tool

@mcp_custom_tool
def surgical_edit_bane_core(target_files: list, fix_description: str):
    """Surgically edits Python files to inject chunking logic using built-in AST tools."""
    chunking_logic = """
# BANE-NLP AUTO-FIX: Message Chunking Utility
def chunk_text(text, limit=4000):
    if not text: return []
    chunks = []
    raw_text = str(text)
    while len(raw_text) > limit:
        idx = raw_text.rfind('\n', 0, limit)
        if idx == -1: idx = limit
        chunks.append(raw_text[:idx].strip())
        raw_text = raw_text[idx:].strip()
    if raw_text: chunks.append(raw_text)
    return chunks
"""
    results = []
    for file_path in target_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Validate with AST first
            ast.parse(content)
            
            if "def chunk_text" not in content:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write('\n' + chunking_logic)
                results.append(f"Surgically injected chunking utility into {file_path}.")
            else:
                results.append(f"Chunking utility already exists in {file_path}. Skipping.")
        except Exception as e:
            results.append(f"Failed {file_path}: {str(e)}")
    return "\n".join(results)