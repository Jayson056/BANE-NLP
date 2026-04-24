"""
BNP Security Module
====================
Input sanitization, payload validation, rate limiting, and user authentication.
"""

import re
import time
from collections import defaultdict

from config import ALLOWED_TELEGRAM_USERS, ALLOWED_MESSENGER_USERS, RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS, PIPELINE_NAME
from core.logger import system_logger


# ──────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────
class RateLimiter:
    """Simple sliding window rate limiter per user."""

    def __init__(self, max_messages: int = RATE_LIMIT_MESSAGES, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self._timestamps: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Check if the user is within their rate limit."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old timestamps
        self._timestamps[user_id] = [
            ts for ts in self._timestamps[user_id] if ts > cutoff
        ]

        if len(self._timestamps[user_id]) >= self.max_messages:
            system_logger.warning(f"Rate limit hit for user {user_id}")
            return False

        self._timestamps[user_id].append(now)
        return True

    def remaining(self, user_id: int) -> int:
        """Return how many messages the user has left in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._timestamps[user_id] = [
            ts for ts in self._timestamps[user_id] if ts > cutoff
        ]
        return max(0, self.max_messages - len(self._timestamps[user_id]))


# Global rate limiter instance
rate_limiter = RateLimiter()


# ──────────────────────────────────────────────
# User Authentication
# ──────────────────────────────────────────────
def is_authorized(user_id: int | str) -> bool:
    """
    Check if a user is authorized to use the bot.
    Handles both Telegram (int) and Messenger (str) IDs.
    PUBLIC ACCESS ENABLED: All users are allowed.
    """
    return True


# ──────────────────────────────────────────────
# Input Sanitization
# ──────────────────────────────────────────────
def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent injection attacks.
    - Strips leading/trailing whitespace
    - Removes null bytes
    - Limits length to 4096 characters
    - Removes control characters (except newlines and tabs)
    """
    if not text:
        return ""

    # Remove null bytes
    text = text.replace("\x00", "")

    # Remove control characters (keep \n and \t)
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Strip whitespace
    text = text.strip()

    # Limit length
    if len(text) > 4096:
        text = text[:4096]

    return text


# ──────────────────────────────────────────────
# Payload Validation
# ──────────────────────────────────────────────
def validate_payload(payload: dict) -> tuple[bool, str]:
    """
    Validate a BNP payload dict.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(payload, dict):
        return False, "Payload is not a dict"

    valid_pipelines = (PIPELINE_NAME, "BNP_PORTFOLIO")
    if payload.get("pipeline") not in valid_pipelines:
        return False, f"Invalid pipeline identifier: {payload.get('pipeline')}"

    if "type" not in payload:
        return False, "Missing 'type' field"

    if payload["type"] not in ("prompt", "response", "log", "status", "ping", "register_service_worker"):
        return False, f"Invalid type: {payload['type']}"

    inner = payload.get("payload")
    if not isinstance(inner, dict):
        return False, "Missing or invalid 'payload' field"

    if payload["type"] == "prompt" and "message" not in inner:
        return False, "Prompt payload missing 'message'"

    if payload["type"] == "response" and "text" not in inner:
        return False, "Response payload missing 'text'"

    return True, ""
