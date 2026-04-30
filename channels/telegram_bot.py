import os
import asyncio
import logging
import re
import time
import subprocess
import httpx
from datetime import datetime
from typing import Optional, Dict, List, Any, Union

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    filters,
    Application
)

from config import (
    TELEGRAM_TOKEN, 
    ALLOWED_TELEGRAM_USERS,
    DEFAULT_TARGET, TARGETS, CHROME_PROFILES,
    MASTER_PROFILES, PROFILE_PASSWORD,
    VOICE_MODELS, DEFAULT_VOICE, CHROME_PATH
)
from core.logger import log_event, log_error, system_logger
from channels.channel_adapter import ChannelAdapter
from core.command_router import CommandRouter

class TelegramChannelAdapter(ChannelAdapter):
    def __init__(self, bot: "Application"):
        self.bot = bot

    @property
    def platform_name(self) -> str:
        return "telegram"

    async def send_text(self, recipient_id: str, text: str, **kwargs) -> Optional[str]:
        pm = kwargs.get("parse_mode")
        msg = await self.bot.bot.send_message(chat_id=recipient_id, text=text, parse_mode=pm, read_timeout=120, write_timeout=120)
        return str(msg.message_id)

    async def send_buttons(self, recipient_id: str, text: str, buttons: List[Dict[str, str]], **kwargs) -> Optional[str]:
        keyboard = []
        for btn in buttons:
            safe_cb = _safe_data(btn["data"])
            keyboard.append([InlineKeyboardButton(btn["label"], callback_data=safe_cb)])
        markup = InlineKeyboardMarkup(keyboard)
        pm = kwargs.get("parse_mode")
        msg = await self.bot.bot.send_message(chat_id=recipient_id, text=text, reply_markup=markup, parse_mode=pm)
        return str(msg.message_id)

    async def edit_message(self, recipient_id: str, message_ref: Any, text: str, buttons: Optional[List[Dict[str, str]]] = None, **kwargs) -> None:
        pm = kwargs.get("parse_mode")
        if isinstance(message_ref, Update) and message_ref.callback_query:
            query = message_ref.callback_query
            markup = None
            if buttons is not None:
                keyboard = []
                for btn in buttons:
                    safe_cb = _safe_data(btn["data"])
                    keyboard.append([InlineKeyboardButton(btn["label"], callback_data=safe_cb)])
                markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=text, reply_markup=markup, parse_mode=pm)

    async def send_typing(self, recipient_id: str) -> None:
        await self.bot.bot.send_chat_action(chat_id=recipient_id, action="typing")

    async def send_image(self, recipient_id: str, image_data: str) -> None:
        await self.bot.bot.send_photo(chat_id=recipient_id, photo=image_data)

    async def send_audio(self, recipient_id: str, file_path: str) -> None:
        with open(file_path, 'rb') as audio:
            await self.bot.bot.send_voice(chat_id=recipient_id, voice=audio, read_timeout=120, write_timeout=120)

    async def send_video(self, recipient_id: str, video_data: str) -> None:
        with open(video_data, 'rb') as video:
            await self.bot.bot.send_video(chat_id=recipient_id, video=video)

    async def delete_message(self, recipient_id: str, message_ref: Any) -> None:
        if isinstance(message_ref, Update) and message_ref.effective_message:
            try:
                await message_ref.effective_message.delete()
            except Exception:
                pass

    async def deliver_response(self, recipient_id: str, res: Union[str, Dict[str, Any]]) -> None:
        """Premium Response Delivery for Telegram (HTML, Buttons, Media)"""
        from channels.telegram_formatter import TelegramFormatter
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        import os

        if not isinstance(res, dict):
            await self.send_text(recipient_id, str(res))
            return

        txt = res.get("text", "No response received.")
        audio = res.get("audio_path")
        imgs = res.get("images", [])
        suggestions = res.get("suggestions", [])
        
        # 1. Format text and extract buttons from text
        formatted_txt, extracted_buttons = TelegramFormatter.format_message(txt)
        final_html = TelegramFormatter.finalize_html(formatted_txt)
        
        # 2. Build Keyboard
        keyboard = []
        seen_data = set()
        
        # Add extracted buttons first
        for btn in extracted_buttons:
            if btn["data"] not in seen_data:
                # We need the local _safe_data helper or a copy of it
                safe_cb = btn["data"].encode('utf-8')[:64].decode('utf-8', 'ignore')
                keyboard.append([InlineKeyboardButton(btn["label"], callback_data=safe_cb)])
                seen_data.add(btn["data"])
        
        # Add suggestions as well
        for sugg in suggestions:
            if sugg not in seen_data:
                safe_cb = sugg.encode('utf-8')[:64].decode('utf-8', 'ignore')
                keyboard.append([InlineKeyboardButton(f"🔍 {sugg}", callback_data=safe_cb)])
                seen_data.add(sugg)
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # 3. Send final text response
        try:
            await self.bot.bot.send_message(chat_id=recipient_id, text=final_html, parse_mode="HTML", reply_markup=reply_markup, read_timeout=120, write_timeout=120)
        except Exception as e:
            log_error("TELEGRAM_DELIVER_TEXT", e)
            try:
                # Fallback to plain text
                await self.bot.bot.send_message(chat_id=recipient_id, text=txt, reply_markup=reply_markup, read_timeout=120, write_timeout=120)
            except: pass
        
        # 4. Send voice
        if audio and os.path.exists(audio):
            try:
                with open(audio, 'rb') as v:
                    await self.bot.bot.send_voice(chat_id=recipient_id, voice=v, read_timeout=120, write_timeout=120)
                os.remove(audio)
            except Exception as e:
                log_error("TELEGRAM_DELIVER_VOICE", e)
        
        # 5. Send images
        for img in imgs:
            try:
                if os.path.exists(img):
                    with open(img, 'rb') as p:
                        await self.bot.bot.send_photo(chat_id=recipient_id, photo=p, read_timeout=120, write_timeout=120)
                else:
                    await self.bot.bot.send_photo(chat_id=recipient_id, photo=img, read_timeout=120, write_timeout=120) # URL
            except Exception as e:
                log_error("TELEGRAM_DELIVER_PHOTO", e)

_WHISPER_MODEL = None

def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel
        _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _WHISPER_MODEL

def _safe_data(data: str) -> str:
    """Safe byte-level truncation for Telegram callback_data (64 byte limit)"""
    if not data: return ""
    encoded = data.encode('utf-8')
    if len(encoded) <= 64:
        return data
    # Truncate and decode with ignore to avoid half-characters
    return encoded[:64].decode('utf-8', 'ignore')

class TelegramBot:
    def __init__(self, bane_core):
        self.core = bane_core
        self.router = CommandRouter(self.core)
        self.adapter = None
        self._user_processing = {}
        self._active_tasks = {}
        # Register ourselves with the core for cross-platform notifications
        self.core.telegram_bot = self

    async def create_standalone_hud(self, chat_id: str, source: str, target: str):
        """
        Creates a real-time HUD for requests NOT originating from Telegram.
        Returns a partial_callback function and the message_id.
        """
        from datetime import datetime
        start_time = datetime.now().strftime('%H:%M:%S')
        
        # Initial message
        text = (
            f"🔔 <b>EXTERNAL REQUEST: {source.upper()}</b>\n"
            f"<code>────────────────────────────</code>\n"
            f"🕒 <b>Time:</b> <code>{start_time}</code>\n"
            f"🛰 <b>Status:</b> <i>Initializing pipeline...</i>"
        )
        
        try:
            msg = await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            msg_id = msg.message_id
        except Exception as e:
            log_error("TELEGRAM_STANDALONE_HUD", e)
            return None

        hud_state = {
            "start_ts": time.time(),
            "last_edit_ts": 0,
            "layer": "L1 Intake",
            "animation_idx": 0
        }

        async def _update_hud_logic(force=False):
            now = time.time()
            if not force and now - hud_state["last_edit_ts"] < 1.5: return
            
            hud_state["animation_idx"] = (hud_state["animation_idx"] + 1) % 4
            dots = "." * hud_state["animation_idx"]
            
            text = f"⚡ <b>{source.upper()} → {target.upper()}</b> | <b>[{hud_state['layer']}]</b> <i>Processing{dots}</i>"

            try:
                await self.app.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode="HTML")
                hud_state["last_edit_ts"] = now
            except: pass

        async def on_partial(chunk):
            if chunk == "__DONE__":
                try:
                    await self.app.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except:
                    # Fallback: if delete fails, just show complete
                    hud_state["status"] = "✅ Complete"
                    await _update_hud_logic(force=True)
                return

            if isinstance(chunk, str):
                asyncio.create_task(_update_hud_logic())
            elif isinstance(chunk, dict) and "status" in chunk:
                status_text = chunk["status"]
                t = status_text.upper()
                if "INTAKE" in t or ("LAYER_1" in t and "1.5" not in t): hud_state["layer"] = "L1 Intake"
                elif "TGPT" in t or "LAYER_1.5" in t: hud_state["layer"] = "L1.5 TGPT"
                elif "PLANNER" in t: hud_state["layer"] = "L2 Plan"
                elif "BRIDGE" in t or "LAYER_3" in t: hud_state["layer"] = "L3 Bridge"
                elif "ANALYZE" in t or "LAYER_4" in t: hud_state["layer"] = "L4 Analyze"
                elif "MCP" in t or "SCHEMA" in t or "LAYER_5" in t: hud_state["layer"] = "L5 MCP"
                elif "RENDERER" in t or "LAYER_6" in t: hud_state["layer"] = "L6 Render"
                elif "RETURN" in t or "LAYER_7" in t: hud_state["layer"] = "L7 Return"
                
                asyncio.create_task(_update_hud_logic())

        return on_partial

    def build(self) -> Application:
        # FIXED: Increased timeouts to prevent Execution Breaches
        app = (
            ApplicationBuilder()
            .token(TELEGRAM_TOKEN)
            .connect_timeout(120.0)
            .read_timeout(120.0)
            .write_timeout(120.0)
            .pool_timeout(120.0)
            .build()
        )
        self.app = app # Store for standalone HUD access
        self.adapter = TelegramChannelAdapter(app)
        app.add_handler(MessageHandler(filters.COMMAND, self._handle_command))
        app.add_handler(CallbackQueryHandler(self._button_handler))
        app.add_handler(MessageHandler(
            (filters.TEXT | filters.VOICE | filters.AUDIO | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, 
            self._handle_message
        ))
        app.add_error_handler(self._error_handler)
        return app

    async def _error_handler(self, update, context):
        from telegram.error import TimedOut, NetworkError
        if isinstance(context.error, (TimedOut, NetworkError)):
            log_error("TELEGRAM_NETWORK", f"API connection issue: {context.error}")
        else:
            log_error("TELEGRAM_BOT_GLOBAL", context.error)

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not update.message: return
        user_id_int = update.effective_user.id
        user_id_str = str(user_id_int)
        
        if ALLOWED_TELEGRAM_USERS and user_id_int not in ALLOWED_TELEGRAM_USERS:
            await update.message.reply_text("⛔ <b>Access Denied:</b> Sorry, you are not an admin.", parse_mode="HTML")
            return

        cmd = update.message.text
        user_name = update.effective_user.first_name or "User"
        
        handled = await self.router.dispatch_command(
            cmd=cmd,
            adapter=self.adapter,
            recipient_id=user_id_str,
            user_name=user_name
        )
        if not handled:
            await update.message.reply_text("❓ Unknown command. Type /help for assistance.")

    async def _button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        try:
            await query.answer()
        except Exception as e:
            if "Query is too old" in str(e) or "query id is invalid" in str(e):
                log_event("TELEGRAM_BOT", "Callback query expired, ignoring.")
            else:
                log_error("TELEGRAM_BUTTON_ANSWER", e)
        user_id = str(update.effective_user.id)
        
        # Route through the shared router
        await self.router.handle_callback(
            callback_data=query.data,
            user_id=user_id,
            adapter=self.adapter,
            recipient_id=user_id,
            message_ref=update
        )

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user: return
        user_id_int = update.effective_user.id
        user_id_str = str(user_id_int)
        chat_id = update.effective_chat.id

        if update.effective_message.from_user.is_bot: return
        
        # Security: Whitelist check
        if ALLOWED_TELEGRAM_USERS and user_id_int not in ALLOWED_TELEGRAM_USERS:
            await update.message.reply_text("⛔ Unauthorized user.")
            return

        message_text = update.effective_message.text or update.effective_message.caption or ""

        # 1. Check for Pending Password Gate
        pw_result = self.router.check_pending_password(user_id_str, message_text)
        if pw_result:
            # Delete password for security
            try: await update.message.delete()
            except: pass

            action = pw_result.get("action")
            if action == "granted":
                target = pw_result["target"]
                profile = pw_result["profile"]
                p_label = CHROME_PROFILES.get(profile, {}).get("label", profile)
                t_label = TARGETS.get(target, {}).get("label", target.upper())
                await update.message.reply_text(
                    f"✅ <b>Access Granted</b>\n\n🔓 Master profile <code>{p_label}</code> activated.\n"
                    f"🚀 Session saved for 8 hours.",
                    parse_mode="HTML"
                )
                # Launch chrome if needed (Router handles state, but Bot triggers launch)
                await self.router.launch_chrome_profile(self.adapter, user_id_str, user_id_str, target, profile)
            elif action == "expired":
                await update.message.reply_text("⏰ Password session expired. Please try again.")
            else:
                await update.message.reply_text("❌ Incorrect password.")
            return

        # 2. Extract Attachments
        file_paths = await self._download_attachments(update, context)
        
        # 3. Trigger Pipeline
        asyncio.create_task(self._process_pipeline(update, context, message_text, file_paths))

    async def _download_attachments(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> List[str]:
        file_paths = []
        msg = update.effective_message
        user_id = update.effective_user.id
        
        try:
            os.makedirs("temp_media", exist_ok=True)
            
            # Photos (take highest resolution)
            if msg.photo:
                photo = await msg.photo[-1].get_file()
                path = os.path.join("temp_media", f"img_{user_id}_{int(time.time())}.jpg")
                await photo.download_to_drive(path)
                file_paths.append(path)
            
            # Voice / Audio
            if msg.voice or msg.audio:
                audio = msg.voice if msg.voice else msg.audio
                audio_file = await audio.get_file()
                ext = ".ogg" if msg.voice else ".mp3"
                path = os.path.join("temp_media", f"audio_{user_id}_{int(time.time())}{ext}")
                await audio_file.download_to_drive(path)
                file_paths.append(path)
                
            # Documents (PDF, etc)
            if msg.document:
                doc = await msg.document.get_file()
                save_dir = os.path.join(os.path.dirname(__file__), "temp_media")
                os.makedirs(save_dir, exist_ok=True)
                path = os.path.join(save_dir, f"doc_{user_id}_{msg.document.file_name}")
                await doc.download_to_drive(path)
                file_paths.append(path)
                
        except Exception as e:
            log_error("TELEGRAM_DOWNLOAD", e)
        return file_paths

    async def _process_pipeline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str, file_paths: List[str]):
        user_id = str(update.effective_user.id)
        target = self.router.get_target(user_id)
        
        # @target override
        tag_match = re.match(r"^@(gemini|notebooklm|chatgpt)\s+(.+)", message_text, re.IGNORECASE | re.DOTALL)
        if tag_match:
            target = tag_match.group(1).lower()
            message_text = tag_match.group(2)

        # Create HUD
        progress_msg = await update.message.reply_text("⚡ <b>BANE Pipeline Initializing...</b>", parse_mode="HTML")
        
        hud_state = {
            "start_ts": time.time(),
            "last_edit_ts": 0,
            "layer": "L1 Intake",
            "animation_idx": 0
        }

        async def _update_hud(force=False):
            now = time.time()
            if not force and now - hud_state["last_edit_ts"] < 1.5: return
            
            hud_state["animation_idx"] = (hud_state["animation_idx"] + 1) % 4
            dots = "." * hud_state["animation_idx"]
            
            text = f"⚡ <b>[{hud_state['layer']}]</b> <i>Processing{dots}</i>"

            try:
                await progress_msg.edit_text(text, parse_mode="HTML")
                hud_state["last_edit_ts"] = now
            except: pass

        # Handle Transcription in background if needed
        voice_files = [f for f in file_paths if "audio_" in f]
        if voice_files:
            hud_state["layer"] = "Voice Mode"
            await _update_hud(force=True)
            
            for vf in voice_files:
                try:
                    model = get_whisper_model()
                    segs, _ = model.transcribe(vf)
                    txt = " ".join([s.text for s in segs])
                    if txt:
                        message_text += f"\n\n🎙 [VOICE TRANSCRIPT]: {txt}"
                except Exception as e:
                    log_error("WHISPER_ERROR", e)

        # Core Request
        hud_state["layer"] = "L1 Intake"
        await _update_hud(force=True)

        try:
            # We use an internal progress callback to update the HUD
            async def on_partial(chunk):
                if chunk == "__DONE__":
                    try: await progress_msg.delete()
                    except: pass
                    return

                if isinstance(chunk, str):
                    asyncio.create_task(_update_hud())
                elif isinstance(chunk, dict) and "status" in chunk:
                    status_text = chunk["status"]
                    t = status_text.upper()
                    
                    if "INTAKE" in t or ("LAYER_1" in t and "1.5" not in t): hud_state["layer"] = "L1 Intake"
                    elif "TGPT" in t or "LAYER_1.5" in t: hud_state["layer"] = "L1.5 TGPT"
                    elif "PLANNER" in t: hud_state["layer"] = "L2 Plan"
                    elif "BRIDGE" in t or "LAYER_3" in t: hud_state["layer"] = "L3 Bridge"
                    elif "ANALYZE" in t or "LAYER_4" in t: hud_state["layer"] = "L4 Analyze"
                    elif "MCP" in t or "SCHEMA" in t or "LAYER_5" in t: hud_state["layer"] = "L5 MCP"
                    elif "RENDERER" in t or "LAYER_6" in t: hud_state["layer"] = "L6 Render"
                    elif "RETURN" in t or "LAYER_7" in t: hud_state["layer"] = "L7 Return"

                    asyncio.create_task(_update_hud())

            res = await self.core.process_request(
                user_id=user_id,
                message=message_text,
                target=target,
                source="Telegram",
                file_paths=file_paths,
                generate_voice=self.router.get_voice_mode(user_id),
                voice_name=self.router.get_voice(user_id),
                chrome_profile=self.router.get_profile(user_id) or "",
                on_partial=on_partial
            )

            # Cleanup HUD (aggressive — try multiple times)
            for _ in range(3):
                try:
                    await progress_msg.delete()
                    break
                except Exception:
                    await asyncio.sleep(0.5)

            # 4. Dispatch final response
            await self.adapter.deliver_response(user_id, res)

        except Exception as e:
            log_error("TELEGRAM_PIPELINE", e)
            try:
                await progress_msg.delete()
            except: pass
            try:
                await progress_msg.edit_text(f"❌ <b>Pipeline Error:</b>\n<code>{str(e)}</code>", parse_mode="HTML")
            except:
                pass
        finally:
            # Cleanup temp files (DISABLED to prevent race conditions with attachments)
            # for f in file_paths:
            #     try: 
            #         if os.path.exists(f): os.remove(f)
            #     except: pass
            pass
