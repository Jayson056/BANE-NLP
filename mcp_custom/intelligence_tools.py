"""
BANE V4 — Intelligence Tools
==============================
Text analysis, summarization helpers, and data extraction utilities.
"""

import re
import os
import json
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event


@mcp_custom_tool(
    name="intelligence_tools.word_count",
    description="Count words, lines, and characters in text or a file. Args: {'text': '...'} or {'path': 'file.txt'}"
)
def word_count(text: str = "", path: str = "") -> str:
    """Count words, lines, and characters."""
    if path:
        if not os.path.exists(path):
            return f"❌ File not found: {path}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    
    if not text:
        return "❌ Error: Provide 'text' or 'path'."
    
    lines = text.count("\n") + 1
    words = len(text.split())
    chars = len(text)
    
    return (
        f"Lines: {lines:,}\n"
        f"Words: {words:,}\n"
        f"Characters: {chars:,}"
    )


@mcp_custom_tool(
    name="intelligence_tools.extract_urls",
    description="Extract all URLs from text or a file. Args: {'text': '...'} or {'path': 'file.txt'}"
)
def extract_urls(text: str = "", path: str = "") -> str:
    """Extract URLs from text content."""
    if path:
        if not os.path.exists(path):
            return f"❌ File not found: {path}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    
    if not text:
        return "❌ Error: Provide 'text' or 'path'."
    
    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
    
    if not urls:
        return "No URLs found."
    
    unique = list(dict.fromkeys(urls))  # Preserve order, remove dupes
    result = f"Found {len(unique)} unique URLs:\n"
    result += "\n".join(f"  🔗 {url}" for url in unique[:30])
    if len(unique) > 30:
        result += f"\n  ... and {len(unique) - 30} more"
    
    return result


@mcp_custom_tool(
    name="intelligence_tools.extract_emails",
    description="Extract all email addresses from text or a file. Args: {'text': '...'}"
)
def extract_emails(text: str = "", path: str = "") -> str:
    """Extract email addresses from text."""
    if path:
        if not os.path.exists(path):
            return f"❌ File not found: {path}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    
    if not text:
        return "❌ Error: Provide 'text' or 'path'."
    
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    
    if not emails:
        return "No email addresses found."
    
    unique = list(dict.fromkeys(emails))
    return f"Found {len(unique)} email addresses:\n" + "\n".join(f"  📧 {e}" for e in unique)


@mcp_custom_tool(
    name="intelligence_tools.diff_files",
    description="Compare two files and show differences. Args: {'file1': 'old.txt', 'file2': 'new.txt'}"
)
def diff_files(file1: str = "", file2: str = "") -> str:
    """Compare two text files."""
    if not file1 or not file2:
        return "❌ Error: Both 'file1' and 'file2' are required."
    
    for f in [file1, file2]:
        if not os.path.exists(f):
            return f"❌ File not found: {f}"
    
    try:
        with open(file1, "r", encoding="utf-8", errors="replace") as f:
            lines1 = f.readlines()
        with open(file2, "r", encoding="utf-8", errors="replace") as f:
            lines2 = f.readlines()
        
        import difflib
        diff = list(difflib.unified_diff(
            lines1, lines2,
            fromfile=file1, tofile=file2,
            lineterm=""
        ))
        
        if not diff:
            return "✅ Files are identical."
        
        output = "\n".join(diff[:100])
        if len(diff) > 100:
            output += f"\n... ({len(diff) - 100} more diff lines)"
        
        return output
    except Exception as e:
        return f"❌ Diff failed: {e}"


@mcp_custom_tool(
    name="intelligence_tools.regex_search",
    description="Search for a regex pattern in text or a file. Args: {'pattern': 'regex', 'text': '...'} or {'pattern': '...', 'path': 'file.py'}"
)
def regex_search(pattern: str = "", text: str = "", path: str = "") -> str:
    """Search for regex pattern matches."""
    if not pattern:
        return "❌ Error: 'pattern' is required."
    
    if path:
        if not os.path.exists(path):
            return f"❌ File not found: {path}"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    
    if not text:
        return "❌ Error: Provide 'text' or 'path'."
    
    try:
        matches = list(re.finditer(pattern, text))
        if not matches:
            return f"No matches found for pattern: {pattern}"
        
        results = [f"Found {len(matches)} matches for /{pattern}/:"]
        for i, m in enumerate(matches[:20]):
            line_num = text[:m.start()].count("\n") + 1
            results.append(f"  [{i+1}] Line {line_num}: {m.group()[:100]}")
        
        if len(matches) > 20:
            results.append(f"  ... and {len(matches) - 20} more matches")
        
        return "\n".join(results)
    except re.error as e:
        return f"❌ Invalid regex: {e}"


@mcp_custom_tool(
    name="intelligence_tools.json_extract",
    description="Extract a value from a JSON file by key path. Args: {'path': 'data.json', 'key': 'users.0.name'}"
)
def json_extract(path: str = "", key: str = "") -> str:
    """Extract value from JSON by dot-notation key path."""
    if not path:
        return "❌ Error: 'path' is required."
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not key:
            return json.dumps(data, indent=2, ensure_ascii=False)[:3000]
        
        # Navigate dot-separated path
        parts = key.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                current = current[int(part)]
            else:
                return f"❌ Cannot navigate '{part}' in {type(current).__name__}"
        
        if isinstance(current, (dict, list)):
            return json.dumps(current, indent=2, ensure_ascii=False)[:2000]
        return str(current)
    except Exception as e:
        return f"❌ JSON extract failed: {e}"
