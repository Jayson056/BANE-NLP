"""
MCP Registry
=============
Discovers and registers all available local tools under the mcp/ directory.
Generates documentation to be injected into the AI prompt so it knows how to use them.

V4 Additions:
  - hot_reload(): Re-scan mcp/ directory and register new tools without restart
  - register_dynamic_tool(): Register a tool from a code string at runtime
  - get_tool_list_summary(): Short summary of all tools for AI self-correction
"""

import os
import sys
import inspect
import importlib
import pkgutil
from typing import Dict, Any, Callable, Optional
from core.logger import log_event, log_error
from mcp.decorators import mcp_tool

# ── Workspace Configuration ──────────────────────────────────────────────────
# Single source of truth for the user's project sandbox path.
# Update this ONE constant if the folder is ever renamed.
PROJECT_WORKSPACE = r"D:\Project_Workspace"

class MCPRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self._dynamic_tools_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "dynamic"
        )
        self._load_all_tools()

    def _load_all_tools(self):
        """Dynamically load all functions decorated with @mcp_tool in mcp/ modules."""
        import mcp
        prefix = mcp.__name__ + "."
        for importer, modname, ispkg in pkgutil.iter_modules(mcp.__path__, prefix):
            try:
                module = importlib.import_module(modname)
                for name, obj in inspect.getmembers(module, inspect.isfunction):
                    if getattr(obj, "_is_mcp_tool", False):
                        tool_name = getattr(obj, "_mcp_tool_name", name)
                        self.tools[tool_name] = obj
            except Exception as e:
                log_error("MCP_REGISTRY", Exception(f"Failed to load {modname}: {e}"))
        
        # Also load dynamic tools from mcp/dynamic/ if they exist
        self._load_dynamic_tools()
                
        log_event("MCP", f"Registered {len(self.tools)} tools.")

    def _load_dynamic_tools(self):
        """Load tools from the mcp/dynamic/ directory (AI-generated tools)."""
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
        
        # Invalidate import caches so new files are detected
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
                    
                    for name, obj in inspect.getmembers(module, inspect.isfunction):
                        if getattr(obj, "_is_mcp_tool", False):
                            tool_name = getattr(obj, "_mcp_tool_name", name)
                            self.tools[tool_name] = obj
                            log_event("MCP", f"[DYNAMIC] Loaded tool: {tool_name}")
                except Exception as e:
                    log_error("MCP_REGISTRY", Exception(f"Failed to load dynamic {filename}: {e}"))

    def hot_reload(self) -> str:
        """Re-scan all mcp/ modules and mcp/dynamic/ for new or updated tools.
        
        This allows the AI to register new tools at runtime without restarting BANE.
        
        Returns:
            Summary string of what was loaded/updated.
        """
        old_count = len(self.tools)
        old_tools = set(self.tools.keys())
        
        # Force reimport all mcp modules to pick up changes
        import mcp
        prefix = mcp.__name__ + "."
        for importer, modname, ispkg in pkgutil.iter_modules(mcp.__path__, prefix):
            if ispkg:
                continue
            try:
                if modname in sys.modules:
                    module = importlib.reload(sys.modules[modname])
                else:
                    module = importlib.import_module(modname)
                
                for name, obj in inspect.getmembers(module, inspect.isfunction):
                    if getattr(obj, "_is_mcp_tool", False):
                        tool_name = getattr(obj, "_mcp_tool_name", name)
                        self.tools[tool_name] = obj
            except Exception as e:
                log_error("MCP_REGISTRY", Exception(f"Failed to reload {modname}: {e}"))
        
        # Also reload dynamic tools
        self._load_dynamic_tools()
        
        new_tools = set(self.tools.keys()) - old_tools
        new_count = len(self.tools)
        
        summary = f"Hot reload complete. {new_count} total tools ({new_count - old_count} new)."
        if new_tools:
            summary += f"\nNew tools: {', '.join(sorted(new_tools))}"
        
        log_event("MCP", f"[HOT RELOAD] {summary}")
        return summary

    def register_dynamic_tool(self, tool_name: str, code: str, description: str = "") -> str:
        """Register a new tool from a Python code string at runtime.
        
        Writes the code to mcp/dynamic/<tool_name>.py and hot-reloads it.
        The tool must use the @mcp_tool decorator.
        
        Args:
            tool_name: The tool's registry name (e.g. 'my_tools.do_thing')
            code: The full Python source code for the tool module
            description: Human-readable description
            
        Returns:
            Success/failure message
        """
        # Ensure dynamic directory exists
        os.makedirs(self._dynamic_tools_dir, exist_ok=True)
        init_path = os.path.join(self._dynamic_tools_dir, "__init__.py")
        if not os.path.exists(init_path):
            with open(init_path, "w") as f:
                f.write("# Auto-generated init for dynamic MCP tools\n")
        
        # Derive filename from tool_name: "my_tools.do_thing" -> "my_tools_do_thing.py"
        safe_name = tool_name.replace(".", "_").replace(" ", "_").lower()
        filepath = os.path.join(self._dynamic_tools_dir, f"{safe_name}.py")
        
        try:
            # Write the code
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            
            # Hot-reload to pick it up
            modname = f"mcp.dynamic.{safe_name}"
            if modname in sys.modules:
                module = importlib.reload(sys.modules[modname])
            else:
                module = importlib.import_module(modname)
            
            # Register any @mcp_tool decorated functions from the module
            registered = []
            for name, obj in inspect.getmembers(module, inspect.isfunction):
                if getattr(obj, "_is_mcp_tool", False):
                    tname = getattr(obj, "_mcp_tool_name", name)
                    self.tools[tname] = obj
                    registered.append(tname)
            
            if registered:
                log_event("MCP", f"[DYNAMIC] Registered {len(registered)} tools from {safe_name}.py: {registered}")
                return f"✅ Dynamic tool(s) registered: {', '.join(registered)}"
            else:
                return f"⚠️ File {safe_name}.py was saved but no @mcp_tool decorated functions were found."
                
        except Exception as e:
            log_error("MCP_REGISTRY", Exception(f"Failed to register dynamic tool {tool_name}: {e}"))
            return f"❌ Failed to register dynamic tool: {e}"

    def get_tool_names(self) -> set[str]:
        """V2 Phase 2: Return a set of all registered tool names for schema validation."""
        return set(self.tools.keys())

    def get_tool_list_summary(self) -> str:
        """Return a compact summary of all registered tools for AI self-correction.
        
        Used when the AI hallucinates a tool name — the pipeline feeds this list
        back so the AI can pick the correct tool.
        """
        if not self.tools:
            return "No tools registered."
        
        lines = ["REGISTERED MCP TOOLS:"]
        for name, func in sorted(self.tools.items()):
            desc = getattr(func, "_mcp_tool_desc", "")
            lines.append(f"  • {name}: {desc}")
        
        lines.append(f"\nTotal: {len(self.tools)} tools available.")
        lines.append("Pick the CORRECT tool name from this list and retry.")
        return "\n".join(lines)

    def get_tool_documentation(self, target: str = "chatgpt") -> str:
        """Generate target-aware tool documentation for prompt injection.
        
        Profiles:
            - notebooklm: COMPACT (~800 tokens) — tight token budget
            - chatgpt/gemini: FULL (~1500 tokens) — workspace map + all examples
        """
        if not self.tools:
            return ""
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_workspace = PROJECT_WORKSPACE
        target = (target or "chatgpt").lower()
        
        # ── Build tool list (shared across all targets) ──
        tool_lines = []
        for name, func in self.tools.items():
            desc = getattr(func, "_mcp_tool_desc", "No description")
            tool_lines.append(f"- {name}: {desc}")
        
        if target == "notebooklm":
            return self._build_compact_prompt(base_dir, project_workspace, tool_lines)
        else:
            return self._build_full_prompt(base_dir, project_workspace, tool_lines)
    
    def _build_compact_prompt(self, base_dir: str, workspace: str, tool_lines: list) -> str:
        """NotebookLM compact prompt (~800 tokens). No workspace tree, 1 example."""
        tts_dir        = os.path.join(base_dir, "temp_audio")
        screenshot_dir = os.path.join(base_dir, "Screenshot")
        docs = [
            "# SYSTEM TOOLS",
            f"Autonomous agent. Working dir: {base_dir}",
            f"User projects: {workspace}",
            "",
            "DESIGNATED SAVE PATHS:",
            f"  🔊 TTS / Audio output -> {tts_dir}",
            f"  📸 Screenshots / Images -> {screenshot_dir}",
            "",
            "RULES: For ANY action (files, commands, URLs) respond with ONLY a JSON block. No explanation before or after.",
            'Format: {"call_tool":"name","args":{...}}',
            "New projects go in D:\\Project_Workspace\\. Don't modify engine files unless asked.",
            "Background servers: use 'start /B'. Avoid ports 3000, 5000, 8765.",
            "",
            "SELF-EVOLUTION: If you need a tool that doesn't exist, create it:",
            '{"call_tool":"meta_tools.create_tool","args":{"tool_name":"...","description":"...","code":"from mcp.mcp_registry import mcp_tool\\n@mcp_tool(name=..."}},',
            "",
            "Tools:",
        ]
        docs.extend(tool_lines)
        docs.extend([
            "",
            "Example: 'list files' -> respond ONLY:",
            '{"call_tool":"file_tools.list_dir","args":{"path":"."}}',
            "",
            "After [TOOL RESULT], present data as BANE NLP using icons, one item per line.",
        ])
        return "\n".join(docs)

    def _build_full_prompt(self, base_dir: str, workspace: str, tool_lines: list) -> str:
        """ChatGPT / Gemini full prompt (~1500 tokens). Workspace map + all examples."""
        tts_dir        = os.path.join(base_dir, "temp_audio")
        screenshot_dir = os.path.join(base_dir, "Screenshot")
        docs = [
            "\n# SYSTEM TOOLS AVAILABLE",
            "You are a fully autonomous agent with DIRECT ACCESS to the host machine.",
            f"Your working directory is: {base_dir}",
            f"User project workspace is: {workspace}",
            "",
            "## DESIGNATED SAVE PATHS (MANDATORY — Always save to these exact folders)",
            f"  🔊 TTS / Voice audio output  →  {tts_dir}",
            f"  📸 Screenshots / Captured images →  {screenshot_dir}",
            "  🖼️ AI-generated images         →  generated_images/ (engine root)",
            "",
            "## CRITICAL EXECUTION RULES",
            "1. If the user asks you to perform ANY action (list files, create folder, run command, fetch URL), you MUST respond with ONLY a JSON tool call block.",
            "2. DO NOT say you cannot access the filesystem — you CAN, via the tools below.",
            "3. DO NOT ask for path clarification. Use '.' for current directory if no path is specified.",
            "4. DO NOT add any explanation text before or after the JSON block when calling a tool.",
            "5. Your response MUST be ONLY the JSON block — nothing else.",
            "6. ALWAYS save TTS/audio files to the designated temp_audio/ folder.",
            "7. ALWAYS save screenshots to the designated Screenshot/ folder.",
            "",
            "## Response Format for Tool Calls",
            "When you need to use a tool, respond with EXACTLY this raw JSON format and nothing else:",
            '{',
            '  "call_tool": "tool_name",',
            '  "args": {"arg1": "value1"}',
            '}',
            "",
            "## Available Tools:",
        ]
        docs.extend(tool_lines)
        
        # ── Self-Evolution Section ──
        docs.extend([
            "",
            "## SELF-EVOLUTION (Create New Tools at Runtime)",
            "If you need a capability that doesn't exist in the tool list above, you can CREATE a new tool by responding with this raw JSON:",
            '{',
            '  "call_tool": "meta_tools.create_tool",',
            '  "args": {',
            '    "tool_name": "my_tools.my_function",',
            '    "description": "What this tool does",',
            '    "code": "from mcp.mcp_registry import mcp_tool\\n\\n@mcp_tool(name=\\"my_tools.my_function\\", description=\\"What it does\\")\\ndef my_function(arg1: str):\\n    return f\\"Result: {arg1}\\""',
            '  }',
            '}',
            "The tool will be instantly available after creation — no restart needed.",
        ])
        
        # ── Workspace Structure (ChatGPT/Gemini only) ──
        docs.extend([
            "",
            "## WORKSPACE STRUCTURE",
            f"Root: {base_dir}",
            "```",
            "Bane_NLP/                         ← BANE Engine Root (DO NOT MODIFY unless explicitly asked)",
            "├── run.py                        ← Main engine entry point",
            "├── config.py                     ← Environment variables & ports",
            "├── bane_core.py                  ← Orchestrator (webhooks, bots, pipeline)",
            "├── telegram_bot.py               ← Telegram async handler",
            "├── messenger_bot.py              ← Facebook Messenger webhook",
            "├── browser_bridge.py             ← WebSocket bridge to Chrome extension",
            "├── database.py                   ← SQLite chat logging",
            "├── voice_engine.py               ← Text-to-Speech engine",
            "├── mcp/                          ← Model Context Protocol (YOUR tools live here)",
            "│   ├── mcp_registry.py           ← Tool registration & discovery",
            "│   ├── command_tools.py          ← Terminal command execution",
            "│   ├── file_tools.py             ← File read/write/list/create",
            "│   ├── web_tools.py              ← HTTP URL fetching",
            "│   └── dynamic/                  ← AI-generated tools (hot-loaded)",
            "├── pipeline/                     ← 7-Layer Processing Engine",
            "│   └── engine.py                 ← Core pipeline logic",
            "├── chrome_extension/             ← Browser plugin for DOM injection",
            f"├── temp_audio/                   ← 🔊 SAVE TTS/AUDIO FILES HERE",
            f"├── Screenshot/                   ← 📸 SAVE SCREENSHOTS HERE",
            "├── generated_images/             ← 🖼️  AI-generated images",
            "├── logs/                         ← All system logs (bnp_system.log, errors_YYYY-MM-DD.txt)",
            "├── NOTEBOOKLM_PERSONA.md         ← Your persona source document",
            "├── AI_SKILLS.md                  ← Your skills & formatting rules",
            "│",
            "└── D:\\Project_Workspace\\       ← ★ USER PROJECT SANDBOX (full access)",
            "    ├── MyPortfolio/              ← Example: Flask portfolio app",
            "    └── (user creates projects here)",
            "```",
            "",
            "## OPERATIONAL RULES FOR FILE OPERATIONS",
            f"1. **Default to {PROJECT_WORKSPACE}:** When the user asks to create a new project, app, script, or folder — ALWAYS create it inside `{PROJECT_WORKSPACE}\\` unless they specify an absolute path.",
            "2. **Core Engine = Read-Only:** Files outside `D:\\Project_Workspace\\` (like `run.py`, `config.py`, `telegram_bot.py`, pipeline files) are part of the BANE engine. Do NOT modify them unless the user EXPLICITLY names the file.",
            f"3. **Use absolute paths:** When working inside `{PROJECT_WORKSPACE}\\`, use the full path (e.g., `{PROJECT_WORKSPACE}\\MyApp\\app.py`).",
            "4. **Background servers:** When starting servers (Flask, Django, Node, etc.), ALWAYS use `start /B` prefix on Windows to prevent blocking the pipeline.",
            "5. **Port safety:** Avoid ports 3000 (engine), 5000 (Messenger webhook), and 8765 (WebSocket bridge).",
            "6. **Auto-Play YouTube:** If the user asks you to PLAY a song or video on YouTube, do NOT just open the search page. Use this EXACT DuckDuckGo I'm feeling lucky URL trick via run_command using Profile 4 (replace QUERY_HERE with the song, joined by +): `start chrome --new-window --profile-directory=\\\"Profile 4\\\" \\\"https://duckduckgo.com/?q=!ducky+youtube+QUERY_HERE\\\"`",
            "7. **Email Communication:** If the user asks you to email, notify, or send a message to an email address, use the `communication_tools.send_email` tool. Default to the system owner's email if no recipient is provided.",
            "8. **Browser Profile Isolation:** For ANY automated web navigation, search, or media task, ALWAYS use the `--profile-directory=\\\"Profile 4\\\"` flag to keep automation inside the Jayson-HOME context.",
            f"9. **TTS Save Path:** All generated voice/TTS files MUST be saved to: {tts_dir}",
            f"10. **Screenshot Save Path:** All captured screenshots MUST be saved to: {screenshot_dir}",
            "11. **Script Writing (CRITICAL):** For complex scripts, code blocks, or any multiline content, ALWAYS use `file_tools.write_file_b64` instead of `write_file`. This avoids 'unterminated string literal' errors caused by JSON escaping. You must perform the Base64 encoding yourself first.",
        ])
        
        # ── Examples (full set for ChatGPT/Gemini) ──
        docs.extend([
            "",
            "## EXAMPLES (Follow these patterns exactly):",
            "",
            "User: 'list all folders and files'",
            "Your response (entire message, nothing else):",
            '{',
            '  "call_tool": "file_tools.list_dir",',
            '  "args": {"path": "."}',
            '}',
            "",
            "User: 'what OS are we running on?'",
            "Your response:",
            '{',
            '  "call_tool": "system_tools.get_sys_info",',
            '  "args": {}',
            '}',
            "",
            "User: 'create a folder named test'",
            "Your response:",
            '{',
            '  "call_tool": "file_tools.create_dir",',
            f'  "args": {{"path": "{PROJECT_WORKSPACE}\\\\test"}}',
            '}',
            "",
            "User: 'read the contents of config.py'",
            "Your response:",
            '{',
            '  "call_tool": "file_tools.read_file",',
            '  "args": {"path": "config.py"}',
            '}',
            "",
            "User: 'Play Multo by Cup of Joe on youtube'",
            "Your response:",
            '{',
            '  "call_tool": "command_tools.run_command",',
            '  "args": {"command": "start chrome --new-window --profile-directory=\\\\\"Profile 4\\\\\" \\\\\"https://duckduckgo.com/?q=!ducky+youtube+multo+by+cup+of+joe\\\\\""}',
            '}',
            "",
            f"User: 'generate TTS and save it'",
            "Your response:",
            '{',
            '  "call_tool": "media_tools.text_to_speech_file",',
            f'  "args": {{"text": "BANE NLP version two introduces...", "output_path": "{tts_dir}/output.ogg", "voice": "en-US-GuyNeural"}}',
            '}',
            "",
            f"User: 'take a screenshot'",
            "Your response:",
            '{',
            '  "call_tool": "desktop_tools.take_screenshot",',
            f'  "args": {{"output_path": "{screenshot_dir}/screenshot.png"}}',
            '}',
            "",
            "User: 'write a python script'",
            "Your response (using B64 for safety):",
            '{',
            '  "call_tool": "file_tools.write_file_b64",',
            '  "args": {',
            f'    "path": "{PROJECT_WORKSPACE}\\\\test.py",',
            '    "b64_content": "cHJpbnQoImhlbGxvIHdvcmxkIik="',
            '  }',
            '}',
            "",
            "REMEMBER: When a tool is needed, output ONLY the JSON block. No greeting, no explanation, no extra text.",
            "After you receive a [TOOL RESULT], present the data naturally to the user following your persona format.",
        ])
            
        return "\n".join(docs)

    async def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Execute a registered tool and return its output as a string."""
        if name not in self.tools:
            hint = (
                f"❌ Error: Tool '{name}' not found.\n\n"
                f"{self.get_tool_list_summary()}\n\n"
                f"💡 HINT: If you need a capability that doesn't exist, create it dynamically!\n"
                f"Use `meta_tools.create_tool` to write Python code for '{name}', "
                f"then immediately call it in your next step."
            )
            return hint
            
        try:
            func = self.tools[name]
            
            # V2 Phase 2: Argument Validation before execution
            sig = inspect.signature(func)
            missing_args = []
            for param_name, param in sig.parameters.items():
                if param.default == inspect.Parameter.empty and param_name not in args:
                    missing_args.append(param_name)
                    
            if missing_args:
                return f"❌ Error: Missing required arguments for tool '{name}': {', '.join(missing_args)}"
                
            # Handle async vs sync
            if inspect.iscoroutinefunction(func):
                result = await func(**args)
            else:
                # Run sync tools in a thread executor to avoid blocking the event loop.
                # This is critical for tools like run_command() that may take seconds.
                import asyncio
                import functools
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,  # Use default ThreadPoolExecutor
                    functools.partial(func, **args)
                )
            return str(result)
        except Exception as e:
            import traceback
            full_trace = traceback.format_exc()
            return f"❌ Tool execution failed: {e}\n\nTraceback:\n{full_trace}"

# Global singleton
registry = MCPRegistry()
