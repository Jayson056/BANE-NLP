import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event
import ast
import difflib

@mcp_custom_tool(
    name="system.multi_replace_file_content",
    description="Use this tool ONLY when you are making MULTIPLE, NON-CONTIGUOUS edits to the same file. You MUST provide EXACT target_content (including whitespace). Args: {'target_file': 'file.py', 'instruction': 'Refactor logic', 'description': 'Updated X and Y', 'replacement_chunks': [{'start_line': 1, 'end_line': 5, 'target_content': 'old1', 'replacement_content': 'new1', 'allow_multiple': False}, {'start_line': 20, 'end_line': 25, 'target_content': 'old2', 'replacement_content': 'new2', 'allow_multiple': False}]}"
)
def multi_replace_file_content(target_file: str, replacement_chunks: list, instruction: str = "", description: str = "") -> str:
    """
    Surgically replaces multiple text chunks in a file. Designed exactly like Antigravity's multi_replace_file_content tool.
    """
    if not os.path.exists(target_file):
        return f"❌ Error: File not found: {target_file}"
        
    try:
        with open(target_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
        original_content = "".join(lines)
        new_lines = lines[:]
        
        # Sort chunks in reverse order by start_line to avoid throwing off line numbers for subsequent replacements
        sorted_chunks = sorted(replacement_chunks, key=lambda x: x.get('start_line', 0), reverse=True)
        
        for chunk in sorted_chunks:
            start_line = chunk.get('start_line')
            end_line = chunk.get('end_line')
            target_content = chunk.get('target_content')
            replacement_content = chunk.get('replacement_content')
            allow_multiple = chunk.get('allow_multiple', False)
            
            if not all([start_line, end_line, target_content is not None, replacement_content is not None]):
                return f"❌ Error: Missing required fields in a replacement chunk. Ensure start_line, end_line, target_content, and replacement_content are provided."
                
            start_idx = max(0, start_line - 1)
            end_idx = min(len(new_lines), end_line)
            search_chunk = "".join(new_lines[start_idx:end_idx])
            
            if target_content not in search_chunk:
                return f"❌ Error: target_content not found between lines {start_line}-{end_line}."
                
            occurrences = search_chunk.count(target_content)
            if occurrences > 1 and not allow_multiple:
                return f"❌ Error: target_content found {occurrences} times in lines {start_line}-{end_line}. Must be unique unless allow_multiple is True."
                
            new_chunk_str = search_chunk.replace(target_content, replacement_content)
            new_chunk_lines = new_chunk_str.splitlines(keepends=True)
            
            new_lines = new_lines[:start_idx] + new_chunk_lines + new_lines[end_idx:]
            
        new_content = "".join(new_lines)
        
        # ─── AST Validation for Python files ───
        if target_file.endswith('.py'):
            try:
                ast.parse(new_content)
            except Exception as e:
                return f"❌ Aborted: This multi-surgical edit would cause a Python syntax error:\n{e}\n\nPlease check your indentation in the replacement_contents."
                
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
        
        log_event("MCP", f"Surgically multi-replaced content in {target_file}")
        return f"✅ Surgical multi-replacement successful on {target_file}.\n\nDiff:\n```diff\n{diff_text}\n```"
        
    except Exception as e:
        return f"❌ Error during surgical multi-replacement: {e}"
