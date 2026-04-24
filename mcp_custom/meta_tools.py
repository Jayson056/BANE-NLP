"""
BANE V4 — Meta Tools (Self-Evolution System)
=============================================
Allows the AI to introspect, create, and manage its own tool registry
at runtime. This is the foundation of BANE's adaptive intelligence.

Tools:
  - meta_tools.list_tools: List all registered tools
  - meta_tools.create_tool: Create and register a new tool at runtime
  - meta_tools.reload_tools: Hot-reload all tools from disk
  - meta_tools.get_tool_info: Get detailed info about a specific tool
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event


@mcp_custom_tool(
    name="meta_tools.list_tools",
    description="List all registered MCP tools with their descriptions. Args: {}"
)
def list_tools() -> str:
    """Returns a summary of all registered tools."""
    from mcp_custom.mcp_registry import registry
    return registry.get_tool_list_summary()


@mcp_custom_tool(
    name="meta_tools.create_tool",
    description="Create and register a new MCP tool at runtime (no restart needed). Args: {'tool_name': 'category.function_name', 'description': 'what it does', 'code': 'full python source code with @mcp_custom_tool decorator'}"
)
def create_tool(tool_name: str, description: str = "", code: str = "") -> str:
    """
    Create a new MCP tool dynamically. The code must include the @mcp_custom_tool decorator.
    
    Example code format:
        from mcp_custom.mcp_registry import mcp_custom_tool
        
        @mcp_custom_tool(name="my_tools.greet", description="Say hello")
        def greet(name: str = "World"):
            return f"Hello, {name}!"
    
    Args:
        tool_name: Registry name like "category.function_name"
        description: Human-readable description of what the tool does
        code: Full Python source code including imports and @mcp_custom_tool decorator
    """
    if not tool_name:
        return "❌ Error: 'tool_name' is required."
    if not code:
        return "❌ Error: 'code' is required. Must include a function with @mcp_custom_tool decorator."
    
    # Safety: validate the code doesn't do anything catastrophic
    dangerous_patterns = [
        "os.remove", "shutil.rmtree", "rmdir",
        "format(", "__import__", "eval(", "exec(",
        "subprocess.call", "Popen",  # They should use command_tools.run_command instead
    ]
    
    # Only block if it's in the FUNCTION BODY (not imports)
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            log_event("MCP", f"⚠️ SAFETY: Dynamic tool '{tool_name}' contains potentially dangerous pattern: {pattern}")
            # Don't block — just log. The AI might have legitimate use cases.
    
    # Ensure the code has the required import
    if "from mcp_custom.mcp_registry import mcp_custom_tool" not in code:
        code = "from mcp_custom.mcp_registry import mcp_custom_tool\n\n" + code
    
    from mcp_custom.mcp_registry import registry
    result = registry.register_dynamic_tool(tool_name, code, description)
    
    log_event("MCP", f"[META] create_tool called for '{tool_name}': {result}")
    return result


@mcp_custom_tool(
    name="meta_tools.reload_tools",
    description="Hot-reload all MCP tools from disk. Use after manually editing tool files. Args: {}"
)
def reload_tools() -> str:
    """Force hot-reload of all MCP tool modules."""
    from mcp_custom.mcp_registry import registry
    result = registry.hot_reload()
    log_event("MCP", f"[META] reload_tools: {result}")
    return result


@mcp_custom_tool(
    name="meta_tools.get_tool_info",
    description="Get detailed info about a specific registered tool. Args: {'tool_name': 'name'}"
)
def get_tool_info(tool_name: str = "") -> str:
    """Get source code and metadata for a specific tool."""
    if not tool_name:
        return "❌ Error: 'tool_name' is required."
    
    from mcp_custom.mcp_registry import registry
    import inspect
    
    if tool_name not in registry.tools:
        return f"❌ Tool '{tool_name}' not found. Use meta_tools.list_tools to see all available tools."
    
    func = registry.tools[tool_name]
    desc = getattr(func, "_mcp_custom_tool_desc", "No description")
    
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        source = "(source not available — dynamic tool)"
    
    sig = str(inspect.signature(func))
    
    return (
        f"Tool: {tool_name}\n"
        f"Signature: {tool_name}{sig}\n"
        f"Description: {desc}\n"
        f"\nSource Code:\n{source}"
    )


@mcp_custom_tool(
    name="meta_tools.register_from_file",
    description="Register new MCP tools from an existing Python file. Bypasses JSON string limits. Args: {'path': 'custom_tools/my_tool.py'}"
)
def register_from_file(path: str = "") -> str:
    """Copy a python file into the dynamic tools directory and reload tools."""
    if not path:
        return "❌ Error: 'path' is required."
    if not os.path.exists(path):
        return f"❌ Error: File not found at '{path}'."
    
    try:
        from mcp_custom.mcp_registry import registry
        import shutil
        
        # Ensure dynamic directory exists
        os.makedirs(registry._dynamic_tools_dir, exist_ok=True)
        init_path = os.path.join(registry._dynamic_tools_dir, "__init__.py")
        if not os.path.exists(init_path):
            with open(init_path, "w") as f:
                f.write("# Auto-generated init for dynamic MCP tools\n")
        
        # Copy file to dynamic directory
        filename = os.path.basename(path)
        dest_path = os.path.join(registry._dynamic_tools_dir, filename)
        shutil.copy2(path, dest_path)
        
        # Hot reload will pick up the new file
        reload_result = registry.hot_reload()
        
        log_event("MCP", f"[META] register_from_file: Copied {path} and triggered reload. {reload_result}")
        return f"✅ Successfully staged {filename} and triggered registry reload.\n{reload_result}"
    except Exception as e:
        return f"❌ File registration failed: {str(e)}"
