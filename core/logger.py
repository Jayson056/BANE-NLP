"""
BNP Logger
==========
Unified logging for the entire Bane Notebook Pipeline.

Features:
  - Single consolidated log file: logs/bnp_system.log  (all events + stdout)
  - Dated error log:              logs/errors_YYYY-MM-DD.txt
  - Conversation log:             logs/conversation-YYYY-MM-DD.txt
  - Telegram error notifier:      register_error_notifier() called by run.py
"""

import os
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional, Callable, Awaitable

from config import LOG_DIR

# ── Directory bootstrap ────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

# ── Single consolidated log file (all pipeline events + stdout) ────────────────
_log_file = os.path.join(LOG_DIR, "bnp_system.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),                                    # Console
        logging.FileHandler(_log_file, encoding="utf-8"),          # logs/bnp_system.log
    ],
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
    """Log a pipeline event to bnp_system.log + console."""
    system_logger.info(f"[{event_type}] {details}")


def log_error(context: str, error) -> None:
    """
    Log an error:
      1. bnp_system.log      (always)
      2. errors_YYYY-MM-DD.txt  (always)
      3. Telegram push       (if notifier registered)

    `error` may be an Exception instance or a plain string.
    """
    if isinstance(error, BaseException):
        error_text = f"{type(error).__name__}: {error}\n{traceback.format_exc()}"
    else:
        error_text = str(error)

    system_logger.error(f"[{context}] {error_text}")
    _write_error_file(context, error_text)
    _push_telegram_error(context, error_text)

