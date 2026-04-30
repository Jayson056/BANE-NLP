import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event
import os
import re
import ast
import difflib

@mcp_custom_tool(
    name="system.surgical_edit",
    description="Perform precise, line-by-line or pattern-based edits on a file. Avoids rewriting the entire file. Ideal for fixing specific errors or changing config values. Args: {'path': 'file.py', 'search': 'old code', 'replace': 'new code', 'line_number': 10, 'is_regex': false}"
)
def surgical_edit(path: str, search: str = None, replace: str = None, line_number: int = None, is_regex: bool = False) -> str:
    """
    Surgically edit a file.
    Args:
        path: Path to the file.
        search: The literal string or regex pattern to find.
        replace: The string to replace it with.
        line_number: (Optional) If provided, replaces this specific line (1-indexed).
        is_regex: (Optional) If true, 'search' is treated as a regular expression.
    """
    if not os.path.exists(path):
        return f"❌ Error: File not found: {path}"
    
    if search is None and line_number is None:
        return "❌ Error: You must provide either 'search' or 'line_number' to locate the edit target."
    if replace is None:
        return "❌ Error: 'replace' content is required."

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        original_content = "".join(lines)
        new_lines = list(lines)
        modified = False
        
        # ─── Mode 1: Line Number ───
        if line_number is not None:
            idx = line_number - 1
            if 0 <= idx < len(new_lines):
                # Preserve indentation if replace is just a fragment? No, user should provide the whole line.
                new_lines[idx] = replace + ('\n' if not replace.endswith('\n') else '')
                modified = True
            else:
                return f"❌ Error: Line number {line_number} is out of range (1-{len(new_lines)})."
        
        # ─── Mode 2: Search and Replace ───
        else:
            if is_regex:
                new_content = re.sub(search, replace, original_content)
                if new_content != original_content:
                    new_lines = new_content.splitlines(keepends=True)
                    modified = True
            else:
                new_content = original_content.replace(search, replace)
                if new_content != original_content:
                    new_lines = new_content.splitlines(keepends=True)
                    modified = True
            
            if not modified:
                return f"❌ Error: Search pattern not found in {path}. Use exact matching or regex."

        if modified:
            new_content = "".join(new_lines)
            
            # ─── Python Syntax Validation ───
            if path.endswith('.py'):
                try:
                    ast.parse(new_content)
                except Exception as e:
                    return f"❌ Aborted: This surgical edit would cause a Python syntax error:\n{e}\n\nPlease check your indentation and syntax."
            
            # ─── Write Changes ───
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # ─── Generate Diff Summary ───
            diff = difflib.unified_diff(
                lines, new_lines, 
                fromfile=f"a/{path}", tofile=f"b/{path}",
                n=2
            )
            diff_text = "".join(diff)
            
            log_event("MCP", f"Surgical Edit success on {path}")
            return f"✅ Successfully performed surgical edit on {path}.\n\nDiff:\n```diff\n{diff_text}\n```"

    except Exception as e:
        return f"❌ Error during surgical edit: {e}"

    return "No changes were made."
