"""
Pipeline Intake (Unified Layer 1)
==================================
Merged from: interpreter.py + guardrails.py

Performs in a single pass:
  1. Detect inline @target overrides
  2. Strip leaked BANE headers
  3. Sanitize input
  4. Classify intent (image / video / document / general)
  5. Safety guardrails (empty check, length limit)

Both original stages were <1ms synchronous regex operations.
Merging them eliminates an unnecessary pipeline boundary.
"""

import re
from pipeline.context import PipelineContext
from core.security import sanitize_input
from core.logger import log_event


# Maximum user prompt size (characters)
MAX_MESSAGE_LENGTH = 100_000


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Intake: Interpret + validate the raw user message in one pass.

    Returns:
        ctx with clean_message, intent, and guardrail results populated.
        If guardrails fail, ctx.error is set and ctx.passed_guardrails is False.
    """
    raw = ctx.raw_message or ""

    # ── Step 1: Detect inline target override: "@gemini explain X" ─────────
    inline_match = re.match(r"^@(gemini|notebooklm|chatgpt)\s+(.+)", raw, re.IGNORECASE | re.DOTALL)
    if inline_match:
        ctx.inline_target = inline_match.group(1).lower()
        raw = inline_match.group(2)

    # ── Step 2: Strip leaked/retried BANE headers ─────────────────────────
    clean_raw = raw
    header_pattern = r'\[(KNOWLEDGE BASE|MANDATORY RULES|AI_SKILLS_DRIVE)\][\s\S]*?\[USER_ID: \d+\]\s*USER:\s*'

    if re.search(header_pattern, raw, flags=re.IGNORECASE):
        clean_raw = re.sub(header_pattern, '', raw, flags=re.IGNORECASE).strip()
        log_event("INTAKE", "Detected and stripped leaked BANE header from input.")

    # ── Step 3: Sanitize ──────────────────────────────────────────────────
    ctx.clean_message = sanitize_input(clean_raw)

    # ── Step 4: Intent classification (keyword-based, fast) ───────────────
    lower = ctx.clean_message.lower()

    image_keywords = [
        "generate image", "create image", "picture of", "artwork",
        "draw", "visualize", "drawing", "painting", "dalle", "dall-e", "sketch"
    ]
    video_keywords = [
        "generate video", "create video", "make a video",
        "sora", "motion", "animate", "video of"
    ]

    if any(kw in lower for kw in image_keywords):
        ctx.intent = "image"
        ctx.is_image_request = True
    elif any(kw in lower for kw in video_keywords):
        ctx.intent = "video"
        ctx.is_video_request = True
    elif ctx.file_paths or ctx.file_datas:
        ctx.intent = "document"
        ctx.has_user_files = True
    else:
        ctx.intent = "general"

    log_event("INTAKE", f"Intent={ctx.intent}, Target Override={ctx.inline_target}")

    # ── Step 5: Guardrails (safety checks) ────────────────────────────────
    ctx.passed_guardrails = True

    # Empty check
    if not ctx.clean_message and not ctx.has_user_files:
        ctx.passed_guardrails = False
        ctx.guardrail_reason = "Empty message with no files."
        ctx.error = "⚠️ Empty message received."
        log_event("INTAKE", f"BLOCKED: {ctx.guardrail_reason}")
        ctx.mark_stage("intake")
        return ctx

    # Length check (protects the NLP components)
    if len(ctx.clean_message or "") > MAX_MESSAGE_LENGTH:
        ctx.passed_guardrails = False
        ctx.guardrail_reason = f"Message exceeds {MAX_MESSAGE_LENGTH} chars ({len(ctx.clean_message)})."
        ctx.error = "⚠️ Message too long. Please shorten your input."
        log_event("INTAKE", f"BLOCKED: {ctx.guardrail_reason}")
        ctx.mark_stage("intake")
        return ctx

    log_event("INTAKE", "Approved — intent classified, guardrails passed.")
    ctx.mark_stage("intake")
    return ctx
