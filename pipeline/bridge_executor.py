"""
Pipeline Bridge Executor (Unified Layer 3)
============================================
Merged from: dispatcher.py + executor.py

Performs the complete browser-bridge cycle in a single stage:
  1. Pre-flight connectivity checks (profile awareness)
  2. Acquire browser lock & dispatch payload via WebSocket
  3. Receive raw response from Chrome extension
  4. Extract text, suggestions, images, files
  5. Generate TTS voice audio
  6. Save AI response to database
  7. Complete AI session tracking

These two stages were always sequential with no async boundary
between them — the dispatcher's output was immediately consumed
by the executor. Merging eliminates unnecessary context handoff.
"""

import os
import base64
import uuid
import asyncio
from typing import Optional, List, Dict, Any

from pipeline.context import PipelineContext
from config import RESPONSE_TIMEOUT, CHROME_PROFILES, VOICE_MODELS
from core.database import save_message, complete_ai_session
from core.logger import log_event, log_error


async def run(
    ctx: PipelineContext,
    bridge,
    browser_lock: asyncio.Lock,
    response_handler,
    voice_engine,
    voice_name: Optional[str] = None
) -> PipelineContext:
    """
    Execute the full browser bridge cycle:
      dispatch → receive → extract → TTS → save

    Args:
        ctx:              The pipeline context with payload ready.
        bridge:           The BrowserBridge instance.
        browser_lock:     asyncio.Lock for FIFO queue processing.
        response_handler: ResponseHandler instance for text extraction.
        voice_engine:     VoiceEngine instance for TTS generation.
        voice_name:       Optional specific voice model to use.
    """
    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1: DISPATCH (formerly dispatcher.py)
    # ══════════════════════════════════════════════════════════════════════

    # ── Pre-flight 1: Basic connection check ──────────────────────────────
    if not bridge.is_connected:
        ctx.error = (
            "❌ <b>No Chrome extension connected.</b>\n\n"
            "Please open Chrome and make sure the BANE extension is active."
        )
        log_event("BRIDGE_EXEC", "[Dispatch] FAILED: No browser connection.")
        ctx.mark_stage("bridge_executor")
        return ctx

    # ── Pre-flight 2: Profile-specific connectivity check ────────────────
    if ctx.chrome_profile:
        profile_open = bridge.is_profile_connected(ctx.chrome_profile, ctx.target)

        if not profile_open:
            p_info  = CHROME_PROFILES.get(ctx.chrome_profile, {})
            p_label = p_info.get("label", ctx.chrome_profile)
            p_emoji = p_info.get("color", "🔵")

            base_target = ctx.target.lower()
            if base_target.startswith("gemini_"):
                base_target = "gemini"

            active_profiles = bridge.get_active_profiles()
            active_for_target = {
                p: t for p, t in active_profiles.items()
                if t == base_target
            }

            if active_for_target:
                open_list = "\n".join(
                    f"  • {CHROME_PROFILES.get(p, {}).get('color', '⚪')} "
                    f"{CHROME_PROFILES.get(p, {}).get('label', p)}"
                    for p in active_for_target
                )
                fallback_hint = f"\n\n📋 <b>Currently open for {base_target.upper()}:</b>\n{open_list}"
            else:
                fallback_hint = f"\n\n⚠️ No {base_target.upper()} tab is currently connected."

            ctx.error = (
                f"🚫 <b>Profile Not Open</b>\n\n"
                f"{p_emoji} <b>{p_label}</b> (<code>{ctx.chrome_profile}</code>) "
                f"is not connected to <b>{ctx.target.upper()}</b>.\n\n"
                f"👉 To use this profile:\n"
                f"  1. Open Chrome with that profile\n"
                f"  2. Navigate to <b>{base_target.capitalize()}</b>\n"
                f"  3. The BANE extension will auto-connect"
                f"{fallback_hint}"
            )
            log_event(
                "BRIDGE_EXEC",
                f"[Dispatch] BLOCKED: Profile '{ctx.chrome_profile}' not connected "
                f"for target '{ctx.target}'. Active profiles: {list(active_profiles.keys())}"
            )
            ctx.mark_stage("bridge_executor")
            return ctx

        log_event(
            "BRIDGE_EXEC",
            f"[Dispatch] Profile '{ctx.chrome_profile}' confirmed connected "
            f"for target '{ctx.target}'. Proceeding."
        )

    # ── Acquire lock and dispatch ─────────────────────────────────────────
    log_event("BRIDGE_EXEC", f"[Dispatch] Request [{ctx.request_id[:8]}] queued. Waiting for browser lock...")

    async with browser_lock:
        log_event(
            "BRIDGE_EXEC",
            f"[Dispatch] Request [{ctx.request_id[:8]}] lock acquired. "
            f"Target: {ctx.target} | Profile: {ctx.chrome_profile or 'any'}"
        )

        try:
            raw_response = await bridge.send_payload(ctx.payload, timeout=RESPONSE_TIMEOUT, on_partial=ctx.on_partial)

            if not raw_response:
                p_info  = CHROME_PROFILES.get(ctx.chrome_profile, {})
                p_label = p_info.get("label", ctx.chrome_profile) if ctx.chrome_profile else ctx.target.upper()
                ctx.error = (
                    f"⏱ <b>No response received.</b>\n\n"
                    f"The {ctx.target.upper()} tab "
                    f"({p_label}) may have been closed or the AI is taking too long.\n"
                    "Use /terminate to cancel or try again."
                )
                log_event("BRIDGE_EXEC", f"[Dispatch] Request [{ctx.request_id[:8]}] timed out / no response.")
            else:
                ctx.raw_response = raw_response
                log_event("BRIDGE_EXEC", f"[Dispatch] Request [{ctx.request_id[:8]}] received response.")

        except ConnectionError as e:
            ctx.error = f"❌ Connection lost during request: {e}"
            log_error("BRIDGE_EXEC", e)
        except Exception as e:
            ctx.error = f"❌ Pipeline error: {e}"
            log_error("BRIDGE_EXEC", e)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2: EXECUTE (formerly executor.py)
    # ══════════════════════════════════════════════════════════════════════

    if ctx.is_failed or not ctx.raw_response:
        ctx.mark_stage("bridge_executor")
        return ctx

    # Extract text
    ctx.response_text = response_handler.extract_text(ctx.raw_response)
    ctx.suggestions = response_handler.extract_suggestions(ctx.raw_response)

    # ── Extract Generated Images from Chrome Extension ──
    raw_images = ctx.raw_response.get("payload", {}).get("images", [])
    if raw_images:
        log_event("BRIDGE_EXEC", f"Found {len(raw_images)} image(s) in AI response payload.")
        saved_paths = _extract_and_save_images(raw_images)
        ctx.images = saved_paths
        log_event("BRIDGE_EXEC", f"Saved {len(saved_paths)} image(s) to disk for delivery.")

    # ── Extract Generated Files (PDF, Sheets, Docs) ──
    raw_files = ctx.raw_response.get("payload", {}).get("files", [])
    if raw_files:
        log_event("BRIDGE_EXEC", f"Found {len(raw_files)} document(s) in AI response payload.")
        saved_doc_paths = _extract_and_save_files(raw_files)
        ctx.files = saved_doc_paths
        log_event("BRIDGE_EXEC", f"Saved {len(saved_doc_paths)} document(s) to disk for delivery.")

        if ctx.response_text and ctx.response_text.startswith("✨"):
            ctx.response_text = "✨ Here's the generated image:"

    # Resolve voice configuration for this specific call
    if ctx.response_text and getattr(ctx, 'generate_voice', True):
        ctx.audio_path = await voice_engine.generate_speech(
            ctx.response_text, 
            override_voice_name=voice_name
        )

    # Archive to database
    if ctx.response_text:
        save_message(ctx.conversation_id, "AI", ctx.response_text)
    complete_ai_session(ctx.session_id, ctx.timestamp)

    log_event("BRIDGE_EXEC", f"[Execute] Text={len(ctx.response_text)} chars, Suggestions={len(ctx.suggestions)}, Images={len(ctx.images)}, Files={len(ctx.files)}, Audio={'yes' if ctx.audio_path else 'no'}")
    ctx.mark_stage("bridge_executor")
    return ctx


# ══════════════════════════════════════════════════════════════════════════
# Private Helpers (from executor.py)
# ══════════════════════════════════════════════════════════════════════════

def _extract_and_save_images(image_data_list: list) -> list:
    """
    Process image data from the Chrome extension and save to local files.
    
    Handles three formats:
      1. Base64 data URLs: 'data:image/png;base64,iVBOR...'
      2. BNP local file paths: 'bnp-local-file:C:\\Users\\...\\Downloads\\image.jpg'
      3. Regular URLs (fallback, saved as-is for Telegram to handle)

    Returns:
        List of local file paths to saved images.
    """
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_images")
    os.makedirs(output_dir, exist_ok=True)
    
    saved_paths = []
    
    for img_data in image_data_list:
        if not img_data or not isinstance(img_data, str):
            continue
            
        try:
            if img_data.startswith("data:image/"):
                # ── Format 1: Base64 Data URL ──
                header, b64_content = img_data.split(",", 1)
                
                ext = "png"  # default
                if "image/jpeg" in header or "image/jpg" in header:
                    ext = "jpg"
                elif "image/webp" in header:
                    ext = "webp"
                elif "image/gif" in header:
                    ext = "gif"
                
                filename = f"gemini_gen_{uuid.uuid4().hex[:12]}.{ext}"
                filepath = os.path.join(output_dir, filename)
                
                img_bytes = base64.b64decode(b64_content)
                with open(filepath, "wb") as f:
                    f.write(img_bytes)
                
                saved_paths.append(filepath)
                log_event("BRIDGE_EXEC", f"Saved base64 image: {filename} ({len(img_bytes)} bytes)")
                
            elif img_data.startswith("bnp-local-file:"):
                # ── Format 2: Chrome Downloads API local file path ──
                local_path = img_data.replace("bnp-local-file:", "").strip()
                
                if os.path.exists(local_path):
                    ext = os.path.splitext(local_path)[1] or ".png"
                    filename = f"gemini_gen_{uuid.uuid4().hex[:12]}{ext}"
                    filepath = os.path.join(output_dir, filename)
                    
                    import shutil
                    shutil.copy2(local_path, filepath)
                    saved_paths.append(filepath)
                    log_event("BRIDGE_EXEC", f"Copied local download: {local_path} → {filename}")
                    
                    try:
                        os.remove(local_path)
                    except:
                        pass
                else:
                    log_event("BRIDGE_EXEC", f"⚠️ Local file not found: {local_path}")
            
            else:
                # ── Format 3: Regular URL ──
                saved_paths.append(img_data)
                log_event("BRIDGE_EXEC", f"Passing through image URL: {img_data[:60]}...")
                
        except Exception as e:
            log_error("BRIDGE_EXEC_IMAGE", e)
            continue
    
    return saved_paths


def _extract_and_save_files(file_data_list: list) -> list:
    """
    Process document data from the Chrome extension and save to local files.
    """
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_files")
    os.makedirs(output_dir, exist_ok=True)
    
    saved_paths = []
    
    for f_data in file_data_list:
        if not f_data or not isinstance(f_data, dict):
            continue
            
        try:
            name = f_data.get("name", f"ai_gen_{uuid.uuid4().hex[:8]}")
            b64_content = f_data.get("data", "")
            
            if not b64_content:
                continue
                
            if b64_content.startswith("data:"):
                b64_content = b64_content.split(",", 1)[1]
                
            content_bytes = base64.b64decode(b64_content)
            
            safe_name = "".join([c for c in name if c.isalnum() or c in (".", "-", "_")]).strip()
            filepath = os.path.join(output_dir, safe_name)
            
            with open(filepath, "wb") as f:
                f.write(content_bytes)
            
            saved_paths.append(filepath)
            log_event("BRIDGE_EXEC", f"Saved generated file: {safe_name} ({len(content_bytes)} bytes)")
                
        except Exception as e:
            log_error("BRIDGE_EXEC_FILE", e)
            continue
    
    return saved_paths
