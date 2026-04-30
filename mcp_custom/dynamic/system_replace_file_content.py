import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event
import ast
import difflib

@mcp_custom_tool(
    name="system.replace_file_content",
    description="Use this tool ONLY when you are making a SINGLE CONTIGUOUS block of edits to the same file. For multiple non-adjacent edits, use system.multi_replace_file_content. Args: {'target_file': 'file.py', 'instruction': 'Fix the loop', 'description': 'Updated loop bounds', 'start_line': 10, 'end_line': 20, 'target_content': '    def old():\\n        pass\\n', 'replacement_content': '    def new():\\n        return True\\n', 'allow_multiple': False}"
)
def replace_file_content(target_file: str, start_line: int, end_line: int, target_content: str, replacement_content: str, allow_multiple: bool = False, instruction: str = "", description: str = "") -> str:
    """
    Surgically replaces text in a file. Designed exactly like the Antigravity replace_file_content tool.
    """
    if not os.path.exists(target_file):
        return f"❌ Error: File not found: {target_file}"
        
    try:
        with open(target_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
        original_content = "".join(lines)
        
        # Determine the exact search space based on lines
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        search_chunk = "".join(lines[start_idx:end_idx])
        
        # Check if target_content exists in the specified chunk
        if target_content not in search_chunk:
            # Fallback: check if it exists ANYWHERE in the file just in case lines were off
            if target_content in original_content:
                return f"❌ Error: target_content found, but NOT within lines {start_line}-{end_line}. Adjust your line numbers."
            else:
                return f"❌ Error: target_content NOT found anywhere in the file. You must match the exact text, including whitespace and indentation."
        
        # Count occurrences in the chunk
        occurrences = search_chunk.count(target_content)
        if occurrences > 1 and not allow_multiple:
            return f"❌ Error: target_content found {occurrences} times within lines {start_line}-{end_line}. It must be unique to avoid accidental replacements. Add more context to target_content."
            
        # Perform surgical replacement on the chunk
        new_chunk = search_chunk.replace(target_content, replacement_content)
        
        # Reconstruct the file
        new_lines = lines[:start_idx] + [new_chunk] + lines[end_idx:]
        new_content = "".join(new_lines)
        
        # ─── AST Validation for Python files ───
        if target_file.endswith('.py'):
            try:
                ast.parse(new_content)
            except Exception as e:
                return f"❌ Aborted: This surgical edit would cause a Python syntax error:\n{e}\n\nPlease check your indentation in replacement_content."
                
        # ─── Write Changes ───
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        # ─── Generate Diff ───
        final_new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            lines, final_new_lines, 
            fromfile=f"a/{target_file}", tofile=f"b/{target_file}",
            n=2
        )
        diff_text = "".join(diff)
        
        log_event("MCP", f"Surgically replaced content in {target_file}")
        return f"✅ Surgical replacement successful on {target_file}.\n\nDiff:\n```diff\n{diff_text}\n```"
        
    except Exception as e:
        return f"❌ Error during surgical replacement: {e}"
