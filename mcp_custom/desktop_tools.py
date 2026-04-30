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

# Absolute path to the BANE engine root
_BANE_DIR = Path(__file__).parent.parent.resolve()
_SCREENSHOT_DIR = _BANE_DIR / "Screenshot"
_SCREENSHOT_DIR.mkdir(exist_ok=True)

@mcp_custom_tool(
    name="desktop_tools.screenshot",
    description="Capture a screenshot. To send to Messenger, you MUST provide recipient_id. Args: {'filename': '', 'recipient_id': ''}"
)
def screenshot(filename: str = "", recipient_id: str = "") -> str:
    """Capture a screenshot and save it, then dispatch to communication channels."""
    if not filename:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = _SCREENSHOT_DIR / f"screenshot_{ts}.png"
    else:
        p = Path(filename)
        if not p.parent or str(p.parent) in (".", ""):
            save_path = _SCREENSHOT_DIR / p.name
        else:
            save_path = p
            save_path.parent.mkdir(parents=True, exist_ok=True)
    
    save_path_str = str(save_path)
    try:
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
        subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if save_path.exists():
            responses = []
            
            # 1. Telegram Dispatch
            try:
                from mcp_custom.communication_tools import send_telegram_file
                tg_status = send_telegram_file(str(save_path))
                responses.append(tg_status)
            except Exception as e:
                responses.append(f"❌ Telegram Failed: {e}")

            # 2. Messenger Dispatch
            if recipient_id:
                try:
                    from core.bane_core import get_core_instance
                    core = get_core_instance()
                    if core and hasattr(core, 'messenger_bot') and core.messenger_bot:
                        import asyncio
                        asyncio.run_coroutine_threadsafe(
                            core.messenger_bot._send_messenger_image(recipient_id, str(save_path)),
                            core.loop
                        )
                        responses.append("✅ Screenshot queued for Messenger.")
                    else:
                        responses.append("❌ Messenger Failed: Bot instance not found.")
                except Exception as e:
                    responses.append(f"❌ Messenger Failed: {e}")

            return f"✅ Screenshot saved: {save_path}\n" + "\n".join(responses)
        else:
            return "❌ Screenshot failed: File not created."
    except Exception as e:
        return f"❌ Screenshot failed: {e}"

@mcp_custom_tool(name="desktop_tools.open_app", description="Open an app.")
def open_app(app: str = "", args: str = "") -> str:
    if not app: return "❌ Error: 'app' is required."
    try:
        cmd = f'start "" "{app}"' if " " in app else f"start {app}"
        if args: cmd += f" {args}"
        subprocess.Popen(cmd, shell=True)
        return f"✅ Launched {app}."
    except Exception as e: return f"❌ Failed: {e}"

@mcp_custom_tool(name="desktop_tools.clipboard_get", description="Read clipboard.")
def clipboard_get() -> str:
    try:
        result = subprocess.run(["powershell", "-Command", "Get-Clipboard"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or "(Empty)"
    except Exception as e: return f"❌ Failed: {e}"

@mcp_custom_tool(name="desktop_tools.clipboard_set", description="Set clipboard.")
def clipboard_set(text: str = "") -> str:
    if not text: return "❌ Error: 'text' is required."
    try:
        subprocess.run(["powershell", "-Command", "Set-Clipboard", "-Value", text], creationflags=subprocess.CREATE_NO_WINDOW)
        return f"✅ Copied {len(text)} chars."
    except Exception as e: return f"❌ Failed: {e}"

@mcp_custom_tool(name="desktop_tools.list_processes", description="List processes.")
def list_processes(filter: str = "") -> str:
    try:
        cmd = f'tasklist /FI "IMAGENAME eq {filter}*" /FO CSV' if filter else 'tasklist /FO CSV /NH'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return "\n".join(result.stdout.strip().split("\n")[:30])
    except Exception as e: return f"❌ Failed: {e}"

@mcp_custom_tool(name="desktop_tools.kill_process", description="Kill a process.")
def kill_process(target: str = "") -> str:
    if not target: return "❌ Error: 'target' is required."
    if target.isdigit() and str(os.getpid()) == target: return "❌ Cannot kill self."
    try:
        cmd = f"taskkill /F /PID {target}" if target.isdigit() else f"taskkill /F /IM {target}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout or f"✅ Kill signal sent to {target}."
    except Exception as e: return f"❌ Failed: {e}"
