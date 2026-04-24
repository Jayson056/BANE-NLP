"""
BNP Payload Builder
====================
Converts user messages into the standard BNP JSON payload format.
"""

import json
import uuid
from datetime import datetime, timezone

from config import PIPELINE_NAME, DEFAULT_TARGET


def build_payload(
    message: str,
    target: str = None,
    source: str = "telegram",
    file_data: dict = None,
    files: list = None,
    chrome_profile: str = ""
) -> dict:
    """
    Build a BNP-standard JSON payload.

    Args:
        message:        The user's prompt text.
        target:         AI target ("gemini" / "notebooklm" / "chatgpt").
        source:         Origin of the message (e.g. "telegram").
        file_data:      Optional single file dict {data, name, mime}.
        files:          Optional list of file dicts.
        chrome_profile: Active Chrome profile directory name (e.g. "Profile 7").
                        The extension ONLY processes messages whose chrome_profile
                        matches its own — empty string means broadcast to all.

    Returns:
        A dictionary representing the BNP payload.
    """
    if target is None:
        target = DEFAULT_TARGET

    # Determine which pipeline identifier to use
    pipeline = "BNP_PORTFOLIO" if target == "gemini_portfolio" else PIPELINE_NAME

    payload = {
        "pipeline": pipeline,
        "id": str(uuid.uuid4()),
        "target": target,
        "source": source,
        "type": "prompt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # chrome_profile gates which extension instance processes this message.
        # Empty string = no filtering (legacy / broadcast behaviour).
        "chrome_profile": chrome_profile,
        "payload": {
            "message": message,
        },
    }

    if file_data:
        payload["payload"]["file"] = file_data

    if files:
        payload["payload"]["files"] = files

    return payload


def build_payload_json(message: str, target: str = None, source: str = "telegram") -> str:
    """
    Build a BNP payload and return it as a JSON string.
    """
    return json.dumps(build_payload(message, target, source))


def parse_response(raw: str) -> dict | None:
    """
    Parse a raw JSON string into a BNP response dict.
    Returns None if the JSON is invalid or not a BNP response.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if data.get("pipeline") not in (PIPELINE_NAME, "BNP_PORTFOLIO"):
        return None

    return data


def build_response_payload(text: str, source: str = "gemini", request_id: str = None) -> dict:
    """
    Build a BNP response payload (used by the browser extension side).
    """
    return {
        "pipeline": PIPELINE_NAME,
        "id": request_id or str(uuid.uuid4()),
        "type": "response",
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "text": text,
        },
    }
