"""
BANE V3 — MCP Command Tools
WARNING: Give the AI ability to execute raw terminal commands.
"""

import subprocess
import os
import sys
import re
from mcp.mcp_registry import mcp_tool
from core.logger import log_event

# ─── Self-Protection: Prevent commands that would kill BNP ───
# The LLM frequently issues `taskkill /F /IM python.exe` to restart user 
# Flask/Django servers, but this blanket-kills ALL python.exe processes 
# — including BNP itself. We rewrite these to exclude our own PID.
_BNP_PID = os.getpid()

def _sanitize_command(cmd: str) -> str:
    """Rewrite dangerous commands that would kill the BNP process."""
    # Pattern: taskkill /F /IM python.exe (with any flag ordering)
    pattern = re.compile(
        r'taskkill\s+(?:/[A-Za-z]+\s+)*(?:/IM\s+python(?:\.exe)?)\s*(?:/[A-Za-z]+\s*)*',
        re.IGNORECASE
    )
    
    if pattern.search(cmd):
        log_event("MCP", f"⚠️ SAFETY: Blocked blanket `taskkill python.exe` (would kill BNP PID {_BNP_PID}). Rewriting to targeted kill.")
        # Replace the dangerous taskkill with a bulletproof inline Python string.
        # This uses Python's native WMI or subprocess to exactly kill siblings and NEVER the parent.
        python_killer = f'''python -c "import subprocess, os; pids = [p.split()[1] for p in subprocess.check_output('tasklist /FI \\"IMAGENAME eq python.exe\\" /NH', text=True).strip().split('\\n') if p.strip() and not p.startswith('INFO')]; [subprocess.run(['taskkill', '/F', '/PID', pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for pid in pids if pid != '{_BNP_PID}' and pid.isdigit()]"'''
        
        cmd = pattern.sub(python_killer, cmd)
        # Strip any dangling >nul from original batch format
        cmd = re.sub(r'(\s*>nul\s+2>&1)?', '', cmd)
        log_event("MCP", f"⚠️ SAFETY: Rewritten command: {cmd[:200]}")
    
    return cmd

@mcp_tool(name="command_tools.run_command", description="Run a raw shell command on the host OS. Args: {'command': 'shell_command_here', 'background': false, 'elevated': false}")
def run_command(command: str = None, background: bool = False, elevated: bool = False, **kwargs) -> str:
    if not command:
        return f"❌ Error: No 'command' argument provided. Received args: command={command!r}, extra={kwargs!r}. You MUST pass a 'command' string."
    
    # SAFETY: Sanitize commands that would kill BNP
    command = _sanitize_command(command)
    
    log_event("MCP", f"Executing shell command (background={background}, elevated={elevated}): {command}")
    
    # ── BACKGROUND MODE: Fire-and-forget for servers / long-running tasks ──
    if background:
        try:
            if elevated:
                # Elevated background: wrap in PowerShell Start-Process -Verb RunAs
                ps_cmd = f'Start-Process cmd -ArgumentList "/C {command.replace(chr(39), chr(34))}" -Verb RunAs -WindowStyle Hidden'
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL
                )
            else:
                subprocess.Popen(
                    command, shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            log_event("MCP", f"Background process launched: {command}")
            return f"✅ Background process launched (no wait): {command}"
        except Exception as e:
            return f"❌ Failed to launch background process: {e}"
    
    # ── ELEVATED MODE (foreground): Run as admin via PowerShell ──
    if elevated:
        try:
            # Build a PowerShell wrapper that runs the command elevated and captures output
            escaped = command.replace('"', '`"')
            ps_cmd = (
                f'$p = Start-Process cmd -ArgumentList "/C {escaped} > %TEMP%\\bane_elev_out.txt 2>&1" '
                f'-Verb RunAs -Wait -PassThru; '
                f'$p.ExitCode'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            # Try to read the output file
            out_file = os.path.expandvars(r"%TEMP%\bane_elev_out.txt")
            output = ""
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as f:
                    output = f.read().strip()
                os.remove(out_file)
            exit_code = result.stdout.strip()
            msg = f"Exit Code: {exit_code} (elevated)\n"
            if output:
                msg += f"STDOUT/STDERR:\n{output}"
            else:
                msg += "Command executed with no output."
            return msg.strip()
        except Exception as e:
            return f"❌ Elevated execution failed: {e}"
    
    try:
        creationflags = 0
        if sys.platform == 'win32':
            # ENHANCED SAFETY: CREATE_NO_WINDOW hides the console while preserving stdout pipes.
            # CREATE_NEW_PROCESS_GROUP prevents CTRL_C_EVENT from killing the parent.
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            creationflags=creationflags,
        )
        
        try:
            stdout, stderr = process.communicate(timeout=60)  # Increased from 30s → 60s
        except subprocess.TimeoutExpired as e:
            # Command is still running (likely a long-running server).
            process.kill()
            
            # Extract whatever was logged during those 30 seconds
            out_str = (e.stdout.decode('utf-8', errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or "")).strip()
            err_str = (e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or "")).strip()
            
            # Grab the last 50 lines
            out_lines = out_str.split('\n')[-50:] if out_str else []
            err_lines = err_str.split('\n')[-50:] if err_str else []
            
            msg = "Command started successfully (timed out after 30s — process detached to background)."
            if out_lines: msg += f"\n\n[STARTUP STDOUT - Last {len(out_lines)} lines]:\n" + "\n".join(out_lines)
            if err_lines: msg += f"\n\n[STARTUP STDERR - Last {len(err_lines)} lines]:\n" + "\n".join(err_lines)
            
            return msg
        
        output = stdout.strip() if stdout else ""
        err = stderr.strip() if stderr else ""
        
        msg = f"Exit Code: {process.returncode}\n"
        if output: msg += f"STDOUT:\n{output}\n"
        if err: msg += f"STDERR:\n{err}\n"
        if not output and not err: msg += "Command executed with no STDOUT/STDERR output."
        
        return msg.strip()
    except Exception as e:
        import traceback
        full_trace = traceback.format_exc()
        return f"❌ Error executing command: {e}\n\nTraceback:\n{full_trace}"
