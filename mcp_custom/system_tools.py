"""
BANE V3 — MCP System Tools
Get OS info, platform architecture, and environment data.
"""

import platform
import os
import sys
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool

@mcp_custom_tool(name="system_tools.get_sys_info", description="Retrieve OS, platform, and python environment details. Args: {}")
def get_sys_info() -> str:
    info = [
        f"OS: {platform.system()} {platform.release()} ({platform.version()})",
        f"Architecture: {platform.machine()}",
        f"Node Name: {platform.node()}",
        f"Python: {sys.version.split()[0]}",
        f"Executable: {sys.executable}",
        f"Current Working Dir: {os.getcwd()}"
    ]
    return "\n".join(info)

@mcp_custom_tool(name="system_tools.get_env", description="Retrieve all environment variables. Args: {}")
def get_env() -> str:
    lines = [f"{k}={v}" for k, v in os.environ.items() if "KEY" not in k.upper() and "TOKEN" not in k.upper()]
    return "\n".join(lines)