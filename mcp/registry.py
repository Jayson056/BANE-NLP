"""
BANE V4 — MCP Registry
=======================
Dynamically discovers and registers all MCP tools from all tool modules
loaded by the V4 architecture, including the new dynamic tools directory.
Includes hot-reload and tool registration at runtime.
"""

import os
import sys
import importlib
import pkgutil
import inspect
from typing import Dict, Callable, Optional

from mcp.mcp_registry import mcp_tool
from core.logger import log_event, log_error


class MCPRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self._dynamic_tools_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "dynamic"
        )
        self._load_all_tools()

    def _load_all_tools(self):
        """Discover and load all MCP tools from all registered modules."""
        # Start with a clean slate (except dynamic tools)
        self.tools = {}
        
        # Discover all mcp packages (includes deployment_tools)
        import mcp
        prefix = mcp.__name__ + "."
        
        # Modules we explicitly want to load
        target_modules = set()
        
        # Add all packages found by pkgutil
        for importer, modname, ispkg in pkgutil.iter_modules(mcp.__path__, prefix):
            if not ispkg:
                target_modules.add(modname)
        
        # Add dynamic tools directory
        target_modules.add("mcp.dynamic")
        
        log_event("MCP_REGISTRY", f"Discovering tools across {len(target_modules)} modules...")
        
        for modname in target_modules:
            try:
                if modname == "mcp.dynamic":
                    # Special handling for dynamic tools directory
                    self._load_dynamic_tools()
                else:
                    # Reload standard modules
                    if modname in sys.modules:
                        module = importlib.reload(sys.modules[modname])
                    else:
                        module = importlib.import_module(modname)
                    
                    # Find all decorated tools
                    self._find_tools_in_module(module, modname)
            except Exception as e:
                log_error("MCP_REGISTRY", f"Failed to load module {modname}: {e}")
        
        log_event("MCP_REGISTRY", f"Registered {len(self.tools)} tools total")
        # print(f"[DEBUG] Registered tools: {list(self.tools.keys())}")

    def _find_tools_in_module(self, module, modname: str):
        """Find all @mcp_tool decorated functions in a module."""
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if getattr(obj, "_is_mcp_tool", False):
                tool_name = getattr(obj, "_mcp_tool_name", name)
                self.tools[tool_name] = obj
                # log_event("MCP_REGISTRY", f"[LOAD] {tool_name}")

    def _load_dynamic_tools(self):
        """Load tools from the mcp/dynamic/ directory."""
        if not os.path.isdir(self._dynamic_tools_dir):
            return
        
        # Ensure dynamic dir is importable
        init_path = os.path.join(self._dynamic_tools_dir, "__init__.py")
        if not os.path.exists(init_path):
            with open(init_path, "w") as f:
                f.write("# Auto-generated init for dynamic MCP tools\n")
        
        base_dir = os.path.dirname(os.path.dirname(self._dynamic_tools_dir))
        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)
        
        importlib.invalidate_caches()
        
        for filename in os.listdir(self._dynamic_tools_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                modname = f"mcp.dynamic.{filename[:-3]}"
                try:
                    # Force reimport to pick up changes
                    if modname in sys.modules:
                        module = importlib.reload(sys.modules[modname])
                    else:
                        module = importlib.import_module(modname)
                    
                    self._find_tools_in_module(module, modname)
                    # log_event("MCP_REGISTRY", f"[LOAD DYNAMIC] {filename[:-3]}")
                except Exception as e:
                    log_error("MCP_REGISTRY", f"Failed to load dynamic {filename}: {e}")

    def hot_reload(self) -> str:
        """Re-scan all mcp/ modules and mcp/dynamic/ for new or updated tools."""
        old_count = len(self.tools)
        old_tools = set(self.tools.keys())
        
        # Reload all modules
        self._load_all_tools()
        
        new_tools = set(self.tools.keys()) - old_tools
        new_count = len(self.tools)
        
        summary = f"Hot reload complete. {new_count} total tools ({new_count - old_count} new)."
        if new_tools:
            summary += f"\nNew tools: {', '.join(sorted(new_tools))}"
        
        log_event("MCP_REGISTRY", f"[HOT RELOAD] {summary}")
        return summary

    def register_dynamic_tool(self, tool_name: str, code: str, description: str = "") -> str:
        """Register a new tool from a Python code string at runtime."""
        if not tool_name.isidentifier() or "." in tool_name:
            return f"❌ Error: tool_name must be a valid Python identifier (no dots)."
        
        # Create the file
        file_path = os.path.join(self._dynamic_tools_dir, f"{tool_name}.py")
        
        try:
            # Add imports and docstring if provided
            imports = "from mcp.mcp_registry import mcp_tool\n"
            if "import pandas" in code:
                imports += "import pandas as pd\n"
            if "import numpy" in code:
                imports += "import numpy as np\n"
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(imports)
                if description:
                    f.write(f'__doc__ = """{description}"""\n\n')
                f.write(code)
            
            # Hot reload to register it
            summary = self.hot_reload()
            
            if tool_name in self.tools:
                return f"✅ Tool '{tool_name}' registered successfully.\n{summary}"
            else:
                return f"❌ Tool '{tool_name}' created but not found after reload.\n{summary}"
        except Exception as e:
            log_error("MCP_REGISTRY", f"Failed to register tool {tool_name}: {e}")
            return f"❌ Error registering tool: {e}"

    def get_tool_code(self, tool_name: str) -> Optional[str]:
        """Get the source code of a registered tool."""
        if tool_name not in self.tools:
            return None
        return inspect.getsource(self.tools[tool_name])

    def get_tool_list_summary(self) -> str:
        """Get a short summary of all available tools (for AI self-awareness)."""
        if not self.tools:
            return "No MCP tools registered."
        
        summary = f"Registered MCP Tools ({len(self.tools)} total):\n"
        for tool_name in sorted(self.tools.keys()):
            tool_obj = self.tools[tool_name]
            doc = inspect.getdoc(tool_obj) or "No description"
            summary += f"""
            Tool: {tool_name}

            {doc}
            """
        
        log_event("MCP_REGISTRY", f"Generated tool summary ({len(self.tools)} tools)")
        return summary

# ── Singleton Instance ─────────────────────────────────────────────────────
# Load all tools on startup
mcp_registry = MCPRegistry()

# Expose @mcp_tool decorator for convenience
mcp_tool = mcp_tool
