"""
BANE V4 — Desktop Tools
=========================
Desktop automation: screenshot capture, app launching, clipboard,
window management, and notifications.
"""

import subprocess
import os
import sys
import datetime
from pathlib import Path
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event

# Absolute path to the BANE engine root (this file lives in mcp/, so go one level up)
_BANE_DIR = Path(__file__).parent.parent.resolve()
_SCREENSHOT_DIR = _BANE_DIR / "Screenshot"
_SCREENSHOT_DIR.mkdir(exist_ok=True)  # Ensure it always exists


@mcp_custom_tool(
    name="desktop_tools.screenshot",
    description="Capture a screenshot of the desktop. Args: {'filename': 'screenshot.png'}"
)
def screenshot(filename: str = "") -> str:
    """Capture a screenshot and save it."""
    if not filename:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = _SCREENSHOT_DIR / f"screenshot_{ts}.png"
    else:
        p = Path(filename)
        # If only a bare filename (no directory) was given, put it in the designated folder
        if not p.parent or str(p.parent) in (".", ""):
            save_path = _SCREENSHOT_DIR / p.name
        else:
            save_path = p
            save_path.parent.mkdir(parents=True, exist_ok=True)
    
    save_path_str = str(save_path)
    try:
        # Use PowerShell's built-in screen capture
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
        $bitmap.Save('{save_path_str.replace(chr(92), chr(47))}')
        $graphics.Dispose()
        $bitmap.Dispose()
        """
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if save_path.exists():
            try:
                from mcp_custom.communication_tools import send_telegram_file
                tg_status = send_telegram_file(str(save_path))
                return f"✅ Screenshot saved to: {save_path}\n{tg_status}"
            except Exception as e:
                return f"✅ Screenshot saved to: {save_path}\n❌ Failed to auto-send to Telegram: {e}"
        else:
            return f"❌ Screenshot failed: {result.stderr or 'File not created'}"
    except Exception as e:
        return f"❌ Screenshot failed: {e}"


@mcp_custom_tool(
    name="desktop_tools.open_app",
    description="Open an application by name or path with optional arguments. Args: {'app': 'notepad', 'args': 'C:\\\\file.txt'}"
)
def open_app(app: str = "", args: str = "") -> str:
    """Launch a desktop application with optional args."""
    if not app:
        return "❌ Error: 'app' is required."
    
    try:
        cmd = f'start "" "{app}"' if " " in app else f"start {app}"
        if args:
            cmd += f" {args}"
        subprocess.Popen(cmd, shell=True)
        log_event("MCP", f"Launched app: {app} {args}")
        return f"✅ Application '{app}' launched{(' with args: ' + args) if args else ''}."
    except Exception as e:
        return f"❌ Failed to open {app}: {e}"


@mcp_custom_tool(
    name="desktop_tools.clipboard_get",
    description="Read the current clipboard text content. Args: {}"
)
def clipboard_get() -> str:
    """Read text from the system clipboard."""
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        content = result.stdout.strip()
        return content if content else "(Clipboard is empty or contains non-text data)"
    except Exception as e:
        return f"❌ Clipboard read failed: {e}"


@mcp_custom_tool(
    name="desktop_tools.clipboard_set",
    description="Copy text to the system clipboard. Args: {'text': 'content to copy'}"
)
def clipboard_set(text: str = "") -> str:
    """Write text to the system clipboard."""
    if not text:
        return "❌ Error: 'text' is required."
    try:
        process = subprocess.Popen(
            ["powershell", "-Command", "Set-Clipboard", "-Value", text],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        process.communicate(timeout=5)
        return f"✅ Copied {len(text)} chars to clipboard."
    except Exception as e:
        return f"❌ Clipboard write failed: {e}"


@mcp_custom_tool(
    name="desktop_tools.list_processes",
    description="List running processes with CPU and memory usage. Args: {'filter': 'chrome'}"
)
def list_processes(filter: str = "") -> str:
    """List running processes, optionally filtered by name."""
    try:
        if filter:
            cmd = f'tasklist /FI "IMAGENAME eq {filter}*" /V /FO CSV'
        else:
            cmd = 'tasklist /FO CSV /NH'
        
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        output = result.stdout.strip()
        if not output or "No tasks" in output:
            return f"No processes found{' matching ' + filter if filter else ''}."
        
        # Limit output to prevent token explosion
        lines = output.split("\n")
        if len(lines) > 30:
            output = "\n".join(lines[:30]) + f"\n... ({len(lines) - 30} more processes)"
        
        return output
    except Exception as e:
        return f"❌ Process listing failed: {e}"


@mcp_custom_tool(
    name="desktop_tools.kill_process",
    description="Kill a process by name or PID. Args: {'target': 'notepad.exe'}"
)
def kill_process(target: str = "") -> str:
    """Kill a process by name or PID."""
    if not target:
        return "❌ Error: 'target' is required (process name or PID)."
    
    # Safety: prevent killing BANE itself
    bnp_pid = str(os.getpid())
    if target == bnp_pid:
        return "❌ SAFETY: Cannot kill the BANE process itself."
    
    # Block blanket python.exe kills
    if target.lower() in ("python.exe", "python"):
        return "❌ SAFETY: Cannot kill all python.exe processes. Use a specific PID instead."
    
    try:
        if target.isdigit():
            cmd = f"taskkill /F /PID {target}"
        else:
            cmd = f"taskkill /F /IM {target}"
        
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = (result.stdout + result.stderr).strip()
        return output or f"✅ Kill command issued for {target}."
    except Exception as e:
        return f"❌ Kill failed: {e}"
