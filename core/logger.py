"""
BNP Logger
==========
Unified logging for the entire Bane Notebook Pipeline.

Features:
  - Single consolidated log file: logs/bnp_system.log  (all events + stdout)
  - Dated error log:              logs/errors_YYYY-MM-DD.txt
  - Conversation log:             logs/conversation-YYYY-MM-DD.txt
  - Telegram error notifier:      register_error_notifier() called by run.py
  - Dashboard event bus:          Real-time event stream for the portfolio dashboard
"""

import os
import asyncio
import logging
import traceback
import time
from collections import deque
from datetime import datetime
from typing import Optional, Callable, Awaitable, List

import re
from config import LOG_DIR
import config

# ── Directory bootstrap ────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

# ── Security Scrubber Filter ───────────────────────────────────────────────────
class CredentialScrubberFilter(logging.Filter):
    """Intercepts log messages and redacts sensitive credentials like tokens and admin IDs."""
    def __init__(self):
        super().__init__()
        self._tokens_to_scrub = []
        # Add telegram token to scrubber list if it exists
        tg_token = getattr(config, "TELEGRAM_TOKEN", None)
        if tg_token and isinstance(tg_token, str):
            self._tokens_to_scrub.append(tg_token)
            
        # Add User IDs to scrubber list
        for uid in getattr(config, "ALLOWED_TELEGRAM_USERS", []):
            self._tokens_to_scrub.append((str(uid), "[ADMIN_TELEGRAM_ID]"))
        for uid in getattr(config, "ALLOWED_MESSENGER_USERS", []):
            self._tokens_to_scrub.append((str(uid), "[ADMIN_MESSENGER_ID]"))

    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            # Scrub tokens
            for token in self._tokens_to_scrub:
                if isinstance(token, tuple):
                    if token[0] in record.msg:
                        record.msg = record.msg.replace(token[0], token[1])
                else:
                    if token in record.msg:
                        record.msg = record.msg.replace(token, "[REDACTED_TOKEN]")
        # Also scrub any formatted arguments if they exist
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, tuple):
                scrubbed_args = []
                for arg in record.args:
                    arg_str = str(arg)
                    for token in self._tokens_to_scrub:
                        if isinstance(token, tuple):
                            if token[0] in arg_str:
                                arg_str = arg_str.replace(token[0], token[1])
                                arg = type(arg)(arg_str) if type(arg) is str else arg_str
                        else:
                            if token in arg_str:
                                arg_str = arg_str.replace(token, "[REDACTED_TOKEN]")
                                arg = type(arg)(arg_str) if type(arg) is str else arg_str
                    scrubbed_args.append(arg)
                record.args = tuple(scrubbed_args)
        return True

# ── Single consolidated log file (all pipeline events + stdout) ────────────────
_log_file = os.path.join(LOG_DIR, "bnp_system.log")

console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(_log_file, encoding="utf-8")

scrubber_filter = CredentialScrubberFilter()
console_handler.addFilter(scrubber_filter)
file_handler.addFilter(scrubber_filter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[console_handler, file_handler],
)

system_logger = logging.getLogger("BNP")

# ── Telegram error notifier hook ───────────────────────────────────────────────
# Registered by run.py after the bot is built. Signature:
#   async def _notifier(message: str) -> None
_telegram_error_notifier: Optional[Callable[[str], Awaitable[None]]] = None


def register_error_notifier(notifier: Callable[[str], Awaitable[None]]) -> None:
    """Register an async callable to push critical errors to Telegram."""
    global _telegram_error_notifier
    _telegram_error_notifier = notifier
    system_logger.info("[LOGGER] Telegram error notifier registered.")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _get_error_log_path() -> str:
    """Return today's dated error log path: logs/errors_YYYY-MM-DD.txt"""
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"errors_{today}.txt")


def _write_error_file(context: str, error_text: str) -> None:
    """Append a formatted error entry to today's error log file."""
    path = _get_error_log_path()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"[{timestamp}] [{context}]\n"
        f"{error_text}\n"
        f"{'─' * 60}\n\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass  # Don't crash the pipeline over a log failure


def _push_telegram_error(context: str, error_text: str) -> None:
    """
    Fire-and-forget: push an error card to the owner's Telegram.
    Safe to call from sync context — spawns a task on the running loop.
    """
    if not _telegram_error_notifier:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    msg = (
        f"🚨 <b>BANE ERROR DETECTED</b>\n"
        f"<code>{'─'*28}</code>\n"
        f"⏱ <b>Time:</b> <code>{ts}</code>\n"
        f"📍 <b>Context:</b> <code>{context}</code>\n"
        f"<code>{'─'*28}</code>\n"
        f"<pre>{error_text[:600]}</pre>"
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_telegram_error_notifier(msg))
    except RuntimeError:
        pass  # No running loop — skip silently


# ── Dashboard Event Bus ────────────────────────────────────────────────────────
# Real-time event stream for the portfolio BANE Dashboard.
# Every log_event() and log_error() call pushes a structured event here.

_DASHBOARD_BUFFER_SIZE = 500
_dashboard_event_buffer: deque = deque(maxlen=_DASHBOARD_BUFFER_SIZE)
_dashboard_subscribers: List[asyncio.Queue] = []
_dashboard_start_time: float = time.time()

# Pipeline state tracking (updated by engine events)
_dashboard_state = {
    "status": "online",           # online | processing | error | offline
    "active_requests": 0,
    "total_processed": 0,
    "total_errors": 0,
    "current_source": None,       # "Telegram" | "Messenger" | "Portfolio"
    "current_iteration": 0,
    "current_phase": "idle",
    "uptime_start": time.time(),
}


def _categorize_event(event_type: str) -> str:
    """Map event types to dashboard categories for color-coding."""
    t = event_type.upper()
    if "ERROR" in t or "FAIL" in t:
        return "error"
    if "ENGINE" in t or "PIPELINE" in t or "LAYER" in t:
        return "pipeline"
    if "BRIDGE" in t:
        return "bridge"
    if "MCP" in t or "TOOL" in t or "SCHEMA" in t:
        return "mcp"
    if "ANALYZE" in t:
        return "analyzer"
    if "MESSENGER" in t:
        return "messenger"
    if "TELEGRAM" in t or "STARTUP" in t:
        return "telegram"
    if "RESPONSE" in t or "RENDERER" in t or "RETURN" in t:
        return "response"
    return "system"


def _push_dashboard_event(event_type: str, details: str, level: str = "info") -> None:
    """Push a structured event to all dashboard subscribers."""
    event = {
        "ts": time.time(),
        "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "type": event_type,
        "category": _categorize_event(event_type),
        "level": level,
        "msg": details[:500],  # Cap message length
    }
    _dashboard_event_buffer.append(event)

    # Update state from significant events
    t = event_type.upper()
    if "ENGINE" in t and "Input" in details:
        _dashboard_state["status"] = "processing"
        _dashboard_state["active_requests"] += 1
        if "Messenger" in details:
            _dashboard_state["current_source"] = "Messenger"
        elif "Telegram" in details:
            _dashboard_state["current_source"] = "Telegram"
        elif "Portfolio" in details:
            _dashboard_state["current_source"] = "Portfolio"
    if "ANALYZE" in t and "Complete" in details:
        _dashboard_state["total_processed"] += 1
        _dashboard_state["active_requests"] = max(0, _dashboard_state["active_requests"] - 1)
        if _dashboard_state["active_requests"] == 0:
            _dashboard_state["status"] = "online"
            _dashboard_state["current_source"] = None
            _dashboard_state["current_phase"] = "idle"
    if "ANALYZE" in t and "iteration" in details.lower():
        import re as _re
        m = _re.search(r"iteration\s+(\d+)", details, _re.IGNORECASE)
        if m:
            _dashboard_state["current_iteration"] = int(m.group(1))
    if level == "error":
        _dashboard_state["total_errors"] += 1

    # Broadcast to all connected SSE subscribers
    dead = []
    for q in _dashboard_subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _dashboard_subscribers.remove(q)
        except ValueError:
            pass


def dashboard_subscribe() -> asyncio.Queue:
    """Subscribe to the dashboard event stream. Returns an asyncio.Queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _dashboard_subscribers.append(q)
    return q


def dashboard_unsubscribe(q: asyncio.Queue) -> None:
    """Remove a subscriber queue."""
    try:
        _dashboard_subscribers.remove(q)
    except ValueError:
        pass


def dashboard_get_state() -> dict:
    """Return the current pipeline state snapshot."""
    return {
        **_dashboard_state,
        "uptime": int(time.time() - _dashboard_state["uptime_start"]),
        "subscribers": len(_dashboard_subscribers),
        "buffer_size": len(_dashboard_event_buffer),
    }


def dashboard_get_recent_events(count: int = 100) -> list:
    """Return the last N events from the buffer."""
    items = list(_dashboard_event_buffer)
    return items[-count:]


# ── Public API ─────────────────────────────────────────────────────────────────

def get_conversation_log_path() -> str:
    """Get today's conversation log file path."""
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"conversation-{today}.txt")


def log_conversation(user_message: str, ai_response: str, target: str = "gemini") -> None:
    """
    Log a conversation exchange to the daily conversation log file.
    """
    log_path = get_conversation_log_path()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"[{timestamp}]\n"
        f"User: {user_message}\n"
        f"\n"
        f"{target.capitalize()}:\n"
        f"{ai_response}\n"
        f"\n"
        f"{'─' * 60}\n\n"
    )
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        system_logger.error(f"Failed to log conversation: {e}")


def log_event(event_type: str, details: str) -> None:
    """Log a pipeline event to bnp_system.log + console + dashboard."""
    system_logger.info(f"[{event_type}] {details}")
    _push_dashboard_event(event_type, details, "info")


def log_error(context: str, error) -> None:
    """
    Log an error:
      1. bnp_system.log      (always)
      2. errors_YYYY-MM-DD.txt  (always)
      3. Telegram push       (if notifier registered)
      4. Dashboard event bus  (always)

    `error` may be an Exception instance or a plain string.
    """
    if isinstance(error, BaseException):
        error_text = f"{type(error).__name__}: {error}\n{traceback.format_exc()}"
    else:
        error_text = str(error)

    system_logger.error(f"[{context}] {error_text}")
    _write_error_file(context, error_text)
    _push_telegram_error(context, error_text)
    _push_dashboard_event(context, error_text[:300], "error")


