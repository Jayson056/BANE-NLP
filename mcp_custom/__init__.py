# MCP (Model Context Protocol) Module
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.decorators import mcp_custom_tool

__all__ = ["mcp_custom_tool"]
