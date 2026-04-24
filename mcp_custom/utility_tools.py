"""
BANE V4 — Utility Tools
=========================
General-purpose utilities: date/time, math, encoding,
text processing, and JSON parsing.
"""

import datetime
import json
import base64
import hashlib
import os
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event


@mcp_custom_tool(
    name="utility_tools.get_datetime",
    description="Get the current date and time. Args: {'timezone': 'Asia/Manila'}"
)
def get_datetime(timezone: str = "Asia/Manila") -> str:
    """Get current date and time with timezone info."""
    now = datetime.datetime.now()
    return (
        f"Date: {now.strftime('%A, %B %d, %Y')}\n"
        f"Time: {now.strftime('%I:%M:%S %p')}\n"
        f"ISO: {now.isoformat()}\n"
        f"Timezone: {timezone} (system local)"
    )


@mcp_custom_tool(
    name="utility_tools.calculate",
    description="Evaluate a mathematical expression safely. Args: {'expression': '2 + 2 * 3'}"
)
def calculate(expression: str = "") -> str:
    """Safely evaluate a math expression."""
    if not expression:
        return "❌ Error: 'expression' is required."
    
    # Safety: only allow math operations
    allowed_chars = set("0123456789+-*/().%** ,eE")
    import math
    allowed_names = {
        "abs": abs, "round": round, "min": min, "max": max,
        "pow": pow, "int": int, "float": float,
        "sqrt": math.sqrt, "pi": math.pi, "e": math.e,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10, "ceil": math.ceil,
        "floor": math.floor,
    }
    
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return f"Expression: {expression}\nResult: {result}"
    except Exception as e:
        return f"❌ Math error: {e}"


@mcp_custom_tool(
    name="utility_tools.encode_base64",
    description="Encode text to base64. Args: {'text': 'hello world'}"
)
def encode_base64(text: str = "") -> str:
    """Encode text to base64."""
    if not text:
        return "❌ Error: 'text' is required."
    encoded = base64.b64encode(text.encode()).decode()
    return f"Base64: {encoded}"


@mcp_custom_tool(
    name="utility_tools.decode_base64",
    description="Decode base64 text. Args: {'text': 'aGVsbG8gd29ybGQ='}"
)
def decode_base64(text: str = "") -> str:
    """Decode base64 to text."""
    if not text:
        return "❌ Error: 'text' is required."
    try:
        decoded = base64.b64decode(text).decode()
        return f"Decoded: {decoded}"
    except Exception as e:
        return f"❌ Decode error: {e}"


@mcp_custom_tool(
    name="utility_tools.hash_text",
    description="Generate hash of text (md5, sha1, sha256). Args: {'text': 'hello', 'algorithm': 'sha256'}"
)
def hash_text(text: str = "", algorithm: str = "sha256") -> str:
    """Generate a hash of the given text."""
    if not text:
        return "❌ Error: 'text' is required."
    
    algo_map = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }
    
    algo = algo_map.get(algorithm.lower())
    if not algo:
        return f"❌ Unsupported algorithm: {algorithm}. Use: md5, sha1, sha256, sha512."
    
    digest = algo(text.encode()).hexdigest()
    return f"Algorithm: {algorithm}\nHash: {digest}"


@mcp_custom_tool(
    name="utility_tools.json_format",
    description="Pretty-print/validate a JSON string. Args: {'json_str': '{...}'}"
)
def json_format(json_str: str = "") -> str:
    """Pretty-print and validate JSON."""
    if not json_str:
        return "❌ Error: 'json_str' is required."
    try:
        data = json.loads(json_str)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return f"✅ Valid JSON:\n{formatted}"
    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON: {e}"


@mcp_custom_tool(
    name="utility_tools.file_size",
    description="Get the size of a file in human-readable format. Args: {'path': 'file.txt'}"
)
def file_size(path: str = "") -> str:
    """Get file size in human-readable format."""
    if not path:
        return "❌ Error: 'path' is required."
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    
    size = os.path.getsize(path)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"File: {path}\nSize: {size:.2f} {unit}"
        size /= 1024
    return f"File: {path}\nSize: {size:.2f} PB"


@mcp_custom_tool(
    name="utility_tools.search_files",
    description="Search for files by name pattern in a directory. Args: {'path': '.', 'pattern': '*.py'}"
)
def search_files(path: str = ".", pattern: str = "*") -> str:
    """Search for files matching a glob pattern."""
    import glob
    try:
        matches = glob.glob(os.path.join(path, "**", pattern), recursive=True)
        if not matches:
            return f"No files matching '{pattern}' found in {path}."
        
        # Limit output
        display = matches[:50]
        result = f"Found {len(matches)} files matching '{pattern}':\n"
        result += "\n".join(f"  📄 {m}" for m in display)
        if len(matches) > 50:
            result += f"\n  ... and {len(matches) - 50} more"
        return result
    except Exception as e:
        return f"❌ Search failed: {e}"
