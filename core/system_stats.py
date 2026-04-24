"""
System Stats Module
===================
Dynamically retrieves hardware and pipeline status data for BANE NLP.
"""
import psutil
import os
import re
import platform
from datetime import datetime
from pathlib import Path

def get_tool_count() -> str:
    """Parses the Knowledge Base to count registered MCP tools."""
    try:
        # Resolve path relative to project root
        kb_path = Path("Docs/InjectionHeaderContext/BANE_NLP_BRAIN_knowledge.md")
        if not kb_path.exists():
            return "61"  # Fallback to last known count
            
        content = kb_path.read_text(encoding="utf-8")
        
        # Priority 1: Look for the explicit total line at the bottom
        match = re.search(r"Total:\s*(\d+)\s*tools\s*available\.", content)
        if match:
            return match.group(1)
            
        # Priority 2: Count the bullet points in the tools section
        sections = content.split("REGISTERED MCP TOOLS")
        if len(sections) > 1:
            tools_section = sections[-1]
            count = tools_section.count("  • ")
            if count > 0: return str(count)
            
        return "61"
    except Exception:
        return "61"

def get_disk_usage() -> str:
    """Returns the disk usage percentage of the primary drive."""
    try:
        usage = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
        return f"{usage.percent}%"
    except:
        return "N/A"

def get_machine_report():
    """Compiles a full dynamic hardware report."""
    import time
    from datetime import timedelta
    uptime_sec = time.time() - psutil.boot_time()
    uptime_str = str(timedelta(seconds=int(uptime_sec)))
    
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "disk": get_disk_usage(),
        "tools": get_tool_count(),
        "os": f"{platform.system()} {platform.release()}",
        "uptime": uptime_str,
        "time": datetime.now().strftime("%H:%M:%S")
    }
