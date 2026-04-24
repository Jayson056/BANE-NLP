"""
MCP Decorators
==============
Shared decorators for MCP tools to avoid circular imports.
"""

def mcp_tool(name: str = None, description: str = "", **kwargs):
    """Decorator to mark a function as an MCP tool."""
    def decorator(func):
        func._is_mcp_tool = True
        func._mcp_tool_name = name or func.__name__
        func._mcp_tool_desc = description or func.__doc__ or ""
        # Store extra metadata (like input_schema) if provided
        func._mcp_tool_schema = kwargs.get("input_schema")
        return func
    return decorator
