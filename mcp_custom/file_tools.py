"""
BANE V3 — MCP File System Tools
Tools for file/folder operations
"""

import os
import shutil
from pathlib import Path
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event

@mcp_custom_tool(name="file_tools.read_file", description="Read file contents. Args: {'path': 'path/to/file'}")
def read_file(path: str = None) -> str:
    try:
        p = Path(path)
        if not p.exists(): return f"Error: File not found {path}"
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {e}"

@mcp_custom_tool(name="file_tools.write_file", description="Write content to a file. Args: {'path':'...', 'content':'...'}")
def write_file(path: str = None, content: str = "") -> str:
    try:
        import ast
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        
        # AST Validation for Python files
        if path.endswith('.py'):
            try:
                ast.parse(content)
                return f"Successfully wrote {len(content)} chars to {path} (Python syntax valid)."
            except Exception as syntax_err:
                return f"Successfully wrote {len(content)} chars to {path}, BUT SYNTAX IS INVALID:\n❌ {type(syntax_err).__name__}: {syntax_err}\n⚠️ You MUST fix this file or the code will crash."
        
        return f"Successfully wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file: {e}"

@mcp_custom_tool(name="file_tools.write_file_b64", description="Write content to a file using Base64 encoding (bypasses JSON escaping issues). Args: {'path':'...', 'b64_content':'...'}")
def write_file_b64(path: str = None, b64_content: str = "") -> str:
    try:
        import base64
        import ast
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = base64.b64decode(b64_content).decode("utf-8")
        p.write_text(content, encoding="utf-8")
        
        # AST Validation for Python files
        if path.endswith('.py'):
            try:
                ast.parse(content)
                return f"Successfully wrote {len(content)} chars to {path} (Python syntax valid)."
            except Exception as syntax_err:
                return f"Successfully wrote {len(content)} chars to {path}, BUT SYNTAX IS INVALID:\n❌ {type(syntax_err).__name__}: {syntax_err}\n⚠️ You MUST fix this file or the code will crash."
        
        return f"Successfully wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing file (B64): {e}"

@mcp_custom_tool(name="file_tools.list_dir", description="List directory contents. Args: {'path':'...'}")
def list_dir(path: str = None) -> str:
    try:
        p = Path(path)
        if not p.is_dir(): return f"Error: Directory not found {path}"
        entries = []
        for e in sorted(p.iterdir()):
            type_str = "DIR" if e.is_dir() else "FILE"
            size = e.stat().st_size if e.is_file() else "-"
            entries.append(f"[{type_str}] {e.name} ({size} bytes)")
        if not entries: return "(Directory is empty)"
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {e}"

@mcp_custom_tool(name="file_tools.rename", description="Rename or move a file/folder. Args: {'src': 'old/path', 'dst': 'new/path'}")
def rename(src: str = None, dst: str = None) -> str:
    """
    Rename or move a file or folder using Python's native os.rename().
    This bypasses Windows shell permission restrictions that block cmd/PowerShell renames.
    Args:
        src: The current path of the file or folder.
        dst: The new path/name for the file or folder.
    """
    if not src or not dst:
        return "❌ Error: Both 'src' and 'dst' are required."
    try:
        src_path = Path(src)
        dst_path = Path(dst)
        if not src_path.exists():
            return f"❌ Error: Source not found: {src}"
        if dst_path.exists():
            return f"❌ Error: Destination already exists: {dst}. Delete it first or choose a different name."
        # Ensure parent directory of destination exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dst_path)
        log_event("MCP", f"Renamed: {src} -> {dst}")
        return f"✅ Successfully renamed:\n  {src}\n  → {dst}"
    except PermissionError as e:
        return (
            f"❌ Permission denied renaming '{src}' to '{dst}'.\n"
            f"Make sure no application (VS Code, Explorer, Terminal) has the folder open.\n"
            f"Error detail: {e}"
        )
    except Exception as e:
        return f"❌ Error renaming: {e}"

@mcp_custom_tool(name="file_tools.move_file", description="Move a file or folder to a new location. Args: {'src': 'source/path', 'dst': 'destination/path'}")
def move_file(src: str = None, dst: str = None) -> str:
    """
    Move a file or folder from src to dst.
    Args:
        src: The source path.
        dst: The destination path (can be a directory or a new full path).
    """
    if not src or not dst:
        return "❌ Error: Both 'src' and 'dst' are required."
    try:
        src_path = Path(src)
        if not src_path.exists():
            return f"❌ Error: Source not found: {src}"
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        result = shutil.move(str(src_path), dst)
        log_event("MCP", f"Moved: {src} -> {result}")
        return f"✅ Successfully moved:\n  {src}\n  → {result}"
    except PermissionError as e:
        return f"❌ Permission denied moving '{src}': {e}"
    except Exception as e:
        return f"❌ Error moving: {e}"

@mcp_custom_tool(name="file_tools.copy_file", description="Copy a file to a new location. Args: {'src': 'source/file.txt', 'dst': 'destination/file.txt'}")
def copy_file(src: str = None, dst: str = None) -> str:
    """
    Copy a file from src to dst.
    Args:
        src: The source file path.
        dst: The destination file path or directory.
    """
    if not src or not dst:
        return "❌ Error: Both 'src' and 'dst' are required."
    try:
        src_path = Path(src)
        if not src_path.exists():
            return f"❌ Error: Source not found: {src}"
        if src_path.is_dir():
            return "❌ Error: Cannot copy a directory with copy_file. Use move_file or command_tools.run_command with xcopy."
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        result = shutil.copy2(str(src_path), dst)
        log_event("MCP", f"Copied: {src} -> {result}")
        return f"✅ Successfully copied:\n  {src}\n  → {result}"
    except Exception as e:
        return f"❌ Error copying: {e}"

@mcp_custom_tool(name="file_tools.delete_file", description="Permanently delete a single file. Args: {'path': 'path/to/file.txt'}")
def delete_file(path: str = None) -> str:
    """
    Permanently delete a single file.
    For safety, this ONLY deletes files — not directories.
    To delete a directory, use command_tools.run_command with 'rmdir /S /Q <path>'.
    Args:
        path: The path of the file to delete.
    """
    if not path:
        return "❌ Error: 'path' is required."
    try:
        p = Path(path)
        if not p.exists():
            return f"❌ Error: File not found: {path}"
        if p.is_dir():
            return (
                f"❌ Safety block: '{path}' is a directory. "
                "This tool only deletes individual files. "
                "Use command_tools.run_command with 'rmdir /S /Q \"<path>\"' for directories."
            )
        p.unlink()
        log_event("MCP", f"Deleted file: {path}")
        return f"✅ Successfully deleted: {path}"
    except PermissionError as e:
        return f"❌ Permission denied deleting '{path}': {e}"
    except Exception as e:
        return f"❌ Error deleting: {e}"

@mcp_custom_tool(name="file_tools.create_dir", description="Create a directory. Args: {'path':'path/to/create'}")
def create_dir(path: str = None) -> str:
    try:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory: {path}"
    except Exception as e:
        return f"Error creating directory: {e}"

@mcp_custom_tool(name="file_tools.read_project_snapshot", description="Traversers a directory and stitches all text-based files into a single output string for whole-project analysis. Automatically ignores .git, node_modules, temp, logs, binaries, cache, etc. Args: {'path':'...dir...'}")
def read_project_snapshot(path: str = None) -> str:
    try:
        p = Path(path)
        if not p.is_dir(): return f"Error: Directory not found {path}"
        
        ignore_dirs = {'.git', 'node_modules', 'temp', 'logs', '__pycache__', 'venv', '.venv', 'build', 'dist', 'BANE_CONTEXT_FILES'}
        ignore_exts = {'.png', '.jpg', '.jpeg', '.gif', '.pdf', '.exe', '.dll', '.so', '.db', '.sqlite', '.sqlite3', '.zip', '.tar', '.gz', '.mp3', '.mp4', '.ogg', '.wav', '.webp', '.mp4', '.mov'}
        
        result_lines = [f"=== PROJECT SNAPSHOT: {path} ==="]
        total_files = 0
        total_lines = 0
        
        for root, dirs, files in os.walk(p):
            # Mutate 'dirs' in place to prevent os.walk from descending into ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith('.')]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ignore_exts or file.startswith('.'):
                    continue
                    
                file_path = Path(root) / file
                
                try:
                    # Attempt to read as utf-8, skip if it's binary or weird encoding
                    content = file_path.read_text(encoding='utf-8')
                    rel_path = file_path.relative_to(p)
                    
                    result_lines.append(f"\n\n--- FILE: {rel_path} ---")
                    result_lines.append(content)
                    total_files += 1
                    total_lines += len(content.splitlines())
                    
                    # Hard limit on project snapshot to avoid massive prompt overflow
                    if total_lines > 15000:
                        result_lines.append(f"\n\n[WARNING]: Snapshot truncated. Reached maximum safe line limit (15000 lines).")
                        result_lines.append(f"\n\n=== END OF SNAPSHOT ({total_files} files stitched) ===")
                        return "\n".join(result_lines)
                        
                except UnicodeDecodeError:
                    pass  # Silently skip binary files
                except Exception as e:
                    result_lines.append(f"\n\n--- FILE: {file_path.relative_to(p)} (ERROR: {e}) ---")
                    
        result_lines.append(f"\n\n=== END OF SNAPSHOT ({total_files} files, {total_lines} total lines stitched) ===")
        return "\n".join(result_lines)
    except Exception as e:
        return f"Error reading project snapshot: {e}"

