"""
Pipeline Planner
=================
Stage 3: Decide the final AI target, create database records,
and determine injection strategy (persona/db skip rules).
"""

from pipeline.context import PipelineContext
from core.database import ensure_user, get_or_create_conversation, save_message, create_ai_session
from config import DEFAULT_TARGET
from core.logger import log_event


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Plan the execution:
    - Resolve final AI target (inline override > user pref > default)
    - Create DB user/conversation/session records
    - Set injection flags based on target
    """
    # Resolve target: inline override takes priority
    if ctx.inline_target:
        ctx.target = ctx.inline_target
    elif not ctx.target or ctx.target == "":
        ctx.target = DEFAULT_TARGET

    # Database pipeline
    ctx.db_user_id = ensure_user(platform=ctx.platform.lower(), platform_user_id=str(ctx.user_id))
    ctx.conversation_id = get_or_create_conversation(user_id=ctx.db_user_id, source_platform=ctx.platform.lower())
    
    # Save incoming message
    if ctx.clean_message:
        save_message(ctx.conversation_id, "USER", ctx.clean_message)

    # AI Session tracking
    ctx.session_id = create_ai_session(ctx.conversation_id, ctx.target)

    # Injection strategy
    # NotebookLM: Skip auto-attachments (AI_SKILLS + DB) because they're pinned as sources
    ctx.skip_persona_injection = (ctx.target == "notebooklm") or ctx.is_image_request or ctx.is_video_request
    ctx.skip_db_injection = (ctx.target == "notebooklm") or ctx.is_image_request or ctx.is_video_request

    log_event("PIPELINE", f"[Planner] Target={ctx.target}, SkipPersona={ctx.skip_persona_injection}, Session={ctx.session_id[:8]}")
    ctx.mark_stage("planner")
    return ctx
