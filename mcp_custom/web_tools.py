"""
BANE V3 — MCP Web Tools
Allows the AI to fetch and interact with the web.
"""

import urllib.request
import re
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event

@mcp_custom_tool(name="web_tools.fetch_url", description="Fetches text content from a URL via HTTP GET. Args: {'url': 'https://example.com'}")
def fetch_url(url: str = None) -> str:
    if not url: return "Error: No URL provided."
    log_event("MCP", f"Fetching URL: {url}")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
            
            # Very basic HTML stripping to save token space
            text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.IGNORECASE|re.DOTALL)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE|re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) > 4000:
                text = text[:4000] + "\n... [TRUNCATED due to length]"
            return text
    except Exception as e:
        return f"Error fetching URL: {e}"
