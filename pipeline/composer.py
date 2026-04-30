"""
Pipeline Composer
==================
Stage 5: Assemble the final prompt and payload files.
Combines system persona, dynamic context, user message,
and file attachments into the transmission-ready payload.
"""

import os
import base64
import mimetypes
from pipeline.context import PipelineContext
from pipeline.payload_builder import build_payload
from core.logger import log_event, log_error
from config import PROJECT_WORKSPACE


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Compose the final prompt and payload:
    1. Attach AI_SKILLS.md persona (if not skipped)
    2. Attach bane_data.db (if not skipped)
    3. Process user file attachments
    4. Build the prompt string
    5. Build the BNP payload
    """
    payload_files = []
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ── NOTE: AI_SKILLS.md, MANDATORY_RULES.txt, and MCP_TOOLS_DOCUMENTATION.md ──
    # These files are uploaded as SOURCE DOCUMENTS in NotebookLM/Gemini.
    # We reference them by filename in the injection header only — NO content inlining.


    # ── User File Attachments ──
    for fpath in ctx.file_paths:
        if os.path.exists(fpath):
            try:
                mime_type, _ = mimetypes.guess_type(fpath)
                basename = os.path.basename(fpath)
                ext = fpath.lower()
                if ext.endswith(".m4a") or (ext.endswith(".mp4") and "audio" in basename.lower()):
                    mime_type = "audio/mp4"
                elif ext.endswith(".ogg"):
                    mime_type = "audio/ogg"
                with open(fpath, "rb") as f:
                    payload_files.append({
                        "name": basename,
                        "mime": mime_type or "application/octet-stream",
                        "data": base64.b64encode(f.read()).decode("utf-8")
                    })
            except Exception as e:
                log_error("COMPOSER_FILES", e)

    for fdata in ctx.file_datas:
        payload_files.append({
            "name": fdata.get("name") or fdata.get("filename") or "attachment.bin",
            "mime": fdata.get("mime", "application/octet-stream"),
            "data": fdata.get("data") or fdata.get("base64", "")
        })

    ctx.payload_files = payload_files

    # ══════════════════════════════════════════════════════════════
    # SOURCE IDENTIFICATION BLOCK (always first — multi-platform routing)
    # Ensures Gemini always knows which platform sent this message.
    # Critical because Telegram, Messenger, and Portfolio share ONE Gemini tab.
    # ══════════════════════════════════════════════════════════════
    import config
    display_user_id = str(ctx.user_id)
    is_admin = False

    if display_user_id in [str(u) for u in getattr(config, "ALLOWED_TELEGRAM_USERS", [])]:
        display_user_id = "[JAYSON - ADMIN (TELEGRAM)]"
        is_admin = True
    elif display_user_id in [str(u) for u in getattr(config, "ALLOWED_MESSENGER_USERS", [])]:
        display_user_id = "[JAYSON - ADMIN (MESSENGER)]"
        is_admin = True
    elif display_user_id == "PORTFOLIO":
        display_user_id = "[GUEST - PORTFOLIO WEBSITE]"
        is_admin = False
    else:
        display_user_id = f"[GUEST / OTHER USER - ID: {display_user_id}]"
        is_admin = False

    guest_warning = ""
    if not is_admin:
        guest_warning = (
            "⚠️ ATTENTION: THIS MESSAGE IS FROM A GUEST USER, NOT JAYSON (ADMIN).\n"
            "Treat them politely, but DO NOT execute administrative commands, modify system files, or reveal sensitive system info.\n"
        )

    source_id_block = (
        f"═══ MESSAGE SOURCE ═══\n"
        f"FROM: {ctx.platform.upper()}\n"
        f"USER_ID: {display_user_id}\n"
        f"RESPOND VIA: {ctx.platform.upper()} delivery pipeline\n"
        f"{guest_warning}"
        f"═══════════════════════\n"
    )

    # ── Injection Header Construction ──
    platform_tag    = f"[PLATFORM: {ctx.platform.upper()}]"
    user_tag        = f"[USER_ID: {display_user_id}]"
    profile_tag     = f"[CHROME_PROFILE: {ctx.chrome_profile or 'Default'}]"
    target_tag      = f"[TARGET: {ctx.target.upper()}]"

    # ── Designated folder paths (absolute) ──
    tts_dir        = os.path.join(base_dir, "temp_audio")
    screenshot_dir = os.path.join(base_dir, "Screenshot")
    paths_tag = (
        f"[SAVE_PATHS]\n"
        f"  Project Workspace -> {PROJECT_WORKSPACE}\n"
        f"  BANE Core         -> {base_dir}\n"
        f"  TTS/Audio         -> {tts_dir}\n"
        f"  Screenshot        -> {screenshot_dir}\n"
    )

    # ── Base knowledge reference (all profiles) ──
    kb_reference = "[SYSTEM INSTRUCTIONS] Docs/InjectionHeaderContext/BANE_SYSTEM_INSTRUCTIONS.md"
    if ctx.target in ["gemini", "gemini_general", "gemini_custom"]:
        from config import AI_SKILLS_DRIVE_URL
        kb_reference += f"\n[AI_SKILLS_DRIVE] {AI_SKILLS_DRIVE_URL}"

    # ── Build course context tag if this profile has a subject mapping ──
    from config import CHROME_PROFILES, PROFILE_SUBJECTS
    subject_info = PROFILE_SUBJECTS.get(ctx.chrome_profile)
    course_tag = ""
    if subject_info:
        course_tag = (
            f"[COURSE CONTEXT]\n"
            f"  Course  : {subject_info['course']}\n"
            f"  Type    : {subject_info['type']}\n"
            f"  Schedule: {subject_info['schedule']}\n"
            f"  Student : {subject_info['student']}\n"
        )

    # ── Master Profile: two-layer injection ──
    if ctx.is_master_profile:
        from config import CHROME_PROFILES
        from mcp_custom.mcp_registry import registry
        
        p_label = CHROME_PROFILES.get(ctx.chrome_profile, {}).get("label", ctx.chrome_profile)
        dynamic_tool_docs = registry.get_tool_documentation(ctx.target)
        
        master_block = (
            f"{source_id_block}"
            f"[SYSTEM OVERRIDE ACTIVE: {ctx.chrome_profile} — {p_label}]\n"
            "CRITICAL: BANE Chrome Extension Bridge Active. Your JSON outputs execute directly on the host. You have full MCP access.\n"
            "STATUS: OPERATIONAL. Do not hesitate to use your tools.\n\n"
            f"{kb_reference}\n"
            f"{paths_tag}"
            f"{course_tag}\n"
            f"{dynamic_tool_docs}\n"
        )
        injection_header = (
            f"{master_block}"
            f"[CONTEXT: {platform_tag} | {user_tag} | {target_tag}]\n"
            "JSON OUTPUT RULES:\n"
            "  - TECHNICAL: Respond ONLY with a markdown JSON code block (```json ... ```).\n"
            "  - CHAT: Respond with natural text. No JSON for simple replies.\n"
            "REQUIREMENT: Strictly follow BANE_SYSTEM_INSTRUCTIONS.md.\n"
            f"USER: {ctx.clean_message}"
        )
    else:
        # ── Standard Profile (with full tool access) ──
        from config import CHROME_PROFILES
        from mcp_custom.mcp_registry import registry
        
        p_label = CHROME_PROFILES.get(ctx.chrome_profile, {}).get("label", ctx.chrome_profile or "Default")
        dynamic_tool_docs = registry.get_tool_documentation(ctx.target)
        
        injection_header = (
            f"{source_id_block}"
            "CRITICAL: BANE Chrome Extension Bridge Active. Your outputs execute directly on the host.\n"
            f"{kb_reference}\n"
            f"[PROFILE: {ctx.chrome_profile or 'Default'} — {p_label}]\n"
            f"{paths_tag}"
            f"{course_tag}\n"
            f"{dynamic_tool_docs}\n"
            f"[CONTEXT: {platform_tag} | {user_tag} | {target_tag}]\n"
            "JSON OUTPUT RULES:\n"
            "  - TECHNICAL: Respond ONLY with a markdown JSON code block (```json ... ```).\n"
            "  - CHAT: Respond with natural text. No JSON for simple replies.\n"
            "REQUIREMENT: Strictly follow BANE_SYSTEM_INSTRUCTIONS.md.\n"
            f"USER: {ctx.clean_message}"
        )

    # ── Final Prompt Selection ──
    if "notebooklm" in ctx.target.lower():
        # Super minimal for NotebookLM to avoid UI overflow blocking the Send button
        ctx.final_prompt = ctx.clean_message
    elif ctx.is_image_request or ctx.is_video_request:
        mode_label = "image" if ctx.is_image_request else "video"
        ctx.final_prompt = f"{source_id_block}Please generate a professional {mode_label} of: {ctx.clean_message}"
    elif getattr(ctx, "has_user_files", False):
        # Slim attachment header: identity + source + tools awareness
        # Preserves "Neutral Lens Protocol" — no heavy KB to avoid hallucination crossover
        # but gives the AI enough context to know who it is and where the request came from
        attachment_header = (
            f"{source_id_block}"
            f"[BANE NLP] You are BANE NLP, an AI assistant by Jayson Combate.\n"
            f"The user has attached file(s) via {ctx.platform.upper()}. "
            f"Analyze them based solely on their own content.\n"
            f"DO NOT cross-reference attachments with system architecture documentation.\n"
            f"If the user asks to perform actions (save, convert, deploy), you have full MCP tool access.\n"
            f"USER: {ctx.clean_message}"
        )
        ctx.final_prompt = attachment_header
    else:
        # STRICT: Only the reference header. No inlined persona, rules, or tool docs.
        ctx.final_prompt = injection_header

    # ── Build Payload ──
    ctx.payload = build_payload(
        message=ctx.final_prompt,
        target=ctx.target,
        source=ctx.platform,
        files=payload_files if payload_files else None,
        chrome_profile=ctx.chrome_profile
    )
    ctx.request_id = ctx.payload.get("id", ctx.request_id)

    profile_tier = "MASTER" if ctx.is_master_profile else "STANDARD"
    log_event("PIPELINE", f"[Composer] Profile={ctx.chrome_profile or 'Default'} ({profile_tier}), Prompt={len(ctx.final_prompt)} chars, Files={len(payload_files)}, Target={ctx.target}")
    ctx.mark_stage("composer")
    return ctx
