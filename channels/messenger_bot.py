"""
BNP Messenger Bot
=================
Messenger interface for receiving user prompts and returning AI responses via Facebook Webhooks.
"""

import os
import json
import asyncio
import aiohttp
import tempfile
import re
import subprocess
try:
    import edge_tts
except ImportError:
    edge_tts = None
from typing import Optional, Dict, List, Any, Union
from aiohttp import web

from config import (
    MESSENGER_ACCESS_TOKEN, 
    MESSENGER_VERIFY_TOKEN, 
    MESSENGER_WEBHOOK_PORT,
    DEFAULT_TARGET,
    TARGETS
)
from core.logger import log_event, log_error, system_logger
from channels.channel_adapter import ChannelAdapter
from core.command_router import CommandRouter

class MessengerChannelAdapter(ChannelAdapter):
    def __init__(self, bot: "MessengerBot"):
        self.bot = bot

    @property
    def platform_name(self) -> str:
        return "messenger"

    async def send_text(self, recipient_id: str, text: str, **kwargs) -> Optional[str]:
        # Messenger doesn't support markdown natively, strip bold/italic tags if simple
        clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
        return await self.bot._send_messenger_message(recipient_id, clean_text)

    async def send_buttons(self, recipient_id: str, text: str, buttons: List[Dict[str, str]], **kwargs) -> Optional[str]:
        clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
        quick_replies = []
        for btn in buttons:
            quick_replies.append({
                "content_type": "text",
                "title": btn["label"][:20],
                "payload": btn["data"]
            })
        return await self.bot._send_messenger_message(recipient_id, clean_text, quick_replies=quick_replies)

    async def edit_message(self, recipient_id: str, message_ref: Any, text: str, buttons: Optional[List[Dict[str, str]]] = None, **kwargs) -> None:
        if buttons:
            await self.send_buttons(recipient_id, text, buttons)
        else:
            await self.send_text(recipient_id, text)

    async def send_typing(self, recipient_id: str) -> None:
        await self.bot._send_sender_action(recipient_id, "typing_on")

    async def send_image(self, recipient_id: str, image_data: str) -> None:
        await self.bot._send_messenger_image(recipient_id, image_data)

    async def send_audio(self, recipient_id: str, file_path: str) -> None:
        await self.bot._send_audio_file(recipient_id, file_path)

    async def send_video(self, recipient_id: str, video_data: str) -> None:
        await self.bot._send_messenger_video(recipient_id, video_data)

    async def deliver_response(self, recipient_id: str, res: Union[str, Dict[str, Any]]) -> None:
        """Unified delivery for Messenger (Text, Quick Replies, Media)"""
        import os
        if not isinstance(res, dict):
            await self.send_text(recipient_id, str(res))
            return

        txt = res.get("text", "")
        suggestions = res.get("suggestions", [])
        audio_path = res.get("audio_path")
        imgs = res.get("images", [])
        vids = res.get("videos", [])

        # 1. Format Text & Suggestions
        full_response_text = ""
        if txt.strip():
            full_response_text = self.bot._humanize_response(txt.strip())
        
        qrs = []
        if suggestions:
            num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
            suggestion_lines = []
            for i, s in enumerate(suggestions[:5]):
                emoji = num_emojis[i]
                suggestion_lines.append(f"{emoji} {s}")
                qrs.append({"content_type": "text", "title": f"{emoji} Tap to ask", "payload": s})
            
            suggestion_block = "\n\n💡 Magtanong pa:\n" + "\n".join(suggestion_lines)
            full_response_text += suggestion_block

        is_speech_on = self.bot.router.get_voice_mode(recipient_id)
        
        # Dispatch Audio
        if is_speech_on and audio_path and os.path.exists(audio_path):
            await self.bot._send_audio_file(recipient_id, audio_path, quick_replies=qrs)
            try: os.remove(audio_path)
            except: pass
            
        # Dispatch Text
        if full_response_text.strip():
            await self.bot._send_messenger_message(recipient_id, full_response_text, quick_replies=qrs)

        # Dispatch Media
        if imgs:
            for img in imgs: await self.bot._send_messenger_image(recipient_id, img)
        if vids:
            for vid in vids: await self.bot._send_messenger_video(recipient_id, vid)


# Lazy-load whisper only when an audio file is actually sent by a user
_WHISPER_MODEL = None

def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        # Import inside function to save ~1.5GB RAM at startup
        from faster_whisper import WhisperModel
        print("🚀 [LAZY-LOAD] Warming up Faster-Whisper 'base' model (CPU)...")
        _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
        print("✅ [LAZY-LOAD] Whisper Model Ready.")
    return _WHISPER_MODEL


class MessengerBot:
    """Messenger interface for BNP using Flask as a webhook server."""

    def __init__(self, bane_core, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.core = bane_core
        self.loop = loop or asyncio.get_event_loop()
        self.router = CommandRouter(self.core)
        self.adapter = MessengerChannelAdapter(self)
        self._processed_mids: set[str] = set()
        self.session: Optional[aiohttp.ClientSession] = None

    async def _send_sender_action(self, recipient_id: str, action: str) -> None:
        if not self.session: return
        url = f"https://graph.facebook.com/v21.0/me/messages?access_token={MESSENGER_ACCESS_TOKEN}"
        payload = {"recipient": {"id": recipient_id}, "sender_action": action}
        try:
            async with self.session.post(url, json=payload, timeout=10) as resp:
                await resp.release()
        except: pass

    async def _react_to_message(self, sender_id: str, message_mid: str, emoji: str = "love") -> None:
        if not self.session or not message_mid: return
        url = f"https://graph.facebook.com/v21.0/{message_mid}/reactions?access_token={MESSENGER_ACCESS_TOKEN}"
        payload = {"reaction": emoji} 
        try:
            async with self.session.post(url, json=payload, timeout=10) as resp:
                await resp.release()
        except: pass

    async def _delete_messenger_message(self, message_id: str) -> None:
        """Delete a bot-sent message from the conversation using the Graph API."""
        if not self.session or not message_id: return
        # Strategy 1: Direct DELETE on the message ID
        url = f"https://graph.facebook.com/v21.0/{message_id}?access_token={MESSENGER_ACCESS_TOKEN}"
        try:
            async with self.session.delete(url, timeout=10) as resp:
                status = resp.status
                body = await resp.text()
                if status == 200:
                    log_event("MESSENGER_HUD", f"Deleted HUD message: {message_id[:30]}...")
                else:
                    log_event("MESSENGER_HUD", f"Delete failed ({status}): {body[:150]}")
        except Exception as e:
            log_error("MESSENGER_HUD_DELETE", e)

    async def _send_messenger_image(self, recipient_id: str, img_data: str) -> None:
        if not self.session: return
        url = f"https://graph.facebook.com/v21.0/me/messages?access_token={MESSENGER_ACCESS_TOKEN}"
        try:
            if img_data.startswith("bnp-local-file:"):
                img_data = img_data.replace("bnp-local-file:", "", 1)
            
            if os.path.exists(img_data):
                import mimetypes
                mime_type, _ = mimetypes.guess_type(img_data)
                filename = os.path.basename(img_data)
                data = aiohttp.FormData()
                data.add_field('recipient', json.dumps({'id': recipient_id}))
                data.add_field('message', json.dumps({'attachment': {'type': 'image', 'payload': {}}}))
                data.add_field('filedata', open(img_data, 'rb'), filename=filename, content_type=mime_type or "image/png")
                async with self.session.post(url, data=data, timeout=60) as resp:
                    await resp.release()
            else:
                payload = {"recipient": {"id": recipient_id}, "message": {"attachment": {"type": "image", "payload": {"url": img_data}}}}
                async with self.session.post(url, json=payload, timeout=60) as resp:
                    await resp.release()
        except Exception as e: log_error("MESSENGER_IMAGE", e)

    async def _send_messenger_video(self, recipient_id: str, video_url: str) -> None:
        if not self.session: return
        url = f"https://graph.facebook.com/v21.0/me/messages?access_token={MESSENGER_ACCESS_TOKEN}"
        try:
            payload = {"recipient": {"id": recipient_id}, "message": {"attachment": {"type": "video", "payload": {"url": video_url}}}}
            async with self.session.post(url, json=payload, timeout=60) as resp:
                await resp.release()
        except Exception as e: log_error("MESSENGER_VIDEO", e)

    async def _send_messenger_message(self, recipient_id: str, text: str, quick_replies: Optional[List[Dict]] = None, reply_to_mid: Optional[str] = None) -> Optional[str]:
        if not self.session: return None
        url = f"https://graph.facebook.com/v21.0/me/messages?access_token={MESSENGER_ACCESS_TOKEN}"
        
        # Facebook Messenger counts message length using UTF-16 code units.
        # Unicode bold chars (U+1D5D4+) are supplementary plane → 2 UTF-16 units each.
        # Using Python len() would undercount, causing Messenger to silently truncate.
        def _utf16_len(s: str) -> int:
            """Count UTF-16 code units (what Facebook Messenger uses for length limits)."""
            return len(s.encode('utf-16-le')) // 2

        max_chunk_size = 1800  # Safe limit in UTF-16 units (Messenger max is 2000)
        chunks = []
        current_chunk = ""
        
        for paragraph in text.split('\n'):
            if _utf16_len(paragraph) > max_chunk_size:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                words = paragraph.split(' ')
                for word in words:
                    while _utf16_len(word) > max_chunk_size:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        chunks.append(word[:max_chunk_size // 2])  # Safe substring
                        word = word[max_chunk_size // 2:]
                        
                    if _utf16_len(current_chunk) + _utf16_len(word) + 1 > max_chunk_size:
                        chunks.append(current_chunk.strip())
                        current_chunk = word + " "
                    else:
                        current_chunk += word + " "
                current_chunk = current_chunk.rstrip() + "\n"
            else:
                if _utf16_len(current_chunk) + _utf16_len(paragraph) + 1 > max_chunk_size:
                    chunks.append(current_chunk.strip())
                    current_chunk = paragraph + "\n"
                else:
                    current_chunk += paragraph + "\n"
                    
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        if not chunks and text:
            chunks = [text[:max_chunk_size // 2]]

        first_mid = None
        for i, chunk in enumerate(chunks):
            msg_payload = {"text": chunk}
            if i == len(chunks) - 1 and quick_replies: msg_payload["quick_replies"] = quick_replies
            p = {"recipient": {"id": recipient_id}, "message": msg_payload, "messaging_type": "RESPONSE"}
            if reply_to_mid and i == 0: p["reply_to"] = {"mid": reply_to_mid}
            try:
                async with self.session.post(url, json=p, timeout=30) as r:
                    res = await r.json()
                    log_event("MESSENGER_SEND_STATUS", f"Recipient: {recipient_id} | Status: {r.status} | Res: {json.dumps(res)}")
                    if i == 0: first_mid = res.get('message_id')
                    await asyncio.sleep(0.05)  # 50ms instead of 500ms
            except Exception as e: 
                log_error("MESSENGER_SEND_FAILED", e)
        return first_mid

    async def _send_audio_file(self, recipient_id: str, file_path: str, quick_replies: Optional[List[Dict]] = None) -> None:
        """Sends an existing audio file to Messenger."""
        if not self.session or not os.path.exists(file_path): return
        try:
            url = f"https://graph.facebook.com/v21.0/me/messages?access_token={MESSENGER_ACCESS_TOKEN}"
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_path)
            filename = os.path.basename(file_path)
            data = aiohttp.FormData()
            data.add_field('recipient', json.dumps({'id': recipient_id}))
            msg_obj = {'attachment': {'type': 'audio', 'payload': {}}}
            if quick_replies: msg_obj["quick_replies"] = quick_replies
            data.add_field('message', json.dumps(msg_obj))
            data.add_field('filedata', open(file_path, 'rb'), filename=filename, content_type=mime_type or "audio/mpeg")
            async with self.session.post(url, data=data, timeout=60) as r:
                await r.release()
        except Exception as e: log_error("MESSENGER_AUDIO_FILE_ERROR", e)

    async def _process_async(self, sender_id: str, message_text: str, attachments: Optional[List[Dict]] = None, message_mid: Optional[str] = None) -> None:
        """The main async processing loop for Messenger."""
        if message_text and message_text.startswith("/"):
            await self._handle_command(sender_id, message_text)
            return

        pw_result = self.router.check_pending_password(sender_id, message_text)
        if pw_result:
            action = pw_result.get("action")
            if action == "expired":
                await self._send_messenger_message(sender_id, "⏰ Password session expired. Please select the profile again.")
            elif action == "granted":
                await self._send_messenger_message(sender_id, f"✅ Access Granted\n\n🔓 Master profile {pw_result['profile']} activated.")
            else:
                await self._send_messenger_message(sender_id, "❌ Incorrect password. Access denied.")
            return

        target = self.router.get_target(sender_id)

        tag_match = re.match(r"^@(gemini|notebooklm|chatgpt)\s+(.+)", message_text, re.IGNORECASE | re.DOTALL)
        if tag_match:
            target = tag_match.group(1).lower()
            message_text = tag_match.group(2)

        # UI Feedback
        asyncio.create_task(self._send_sender_action(sender_id, "mark_seen"))
        asyncio.create_task(self._send_sender_action(sender_id, "typing_on"))
        if message_mid: asyncio.create_task(self._react_to_message(sender_id, message_mid))

        file_paths = []
        if attachments and self.session:
            log_event("MESSENGER", f"Processing {len(attachments)} attachments...")
            for att in attachments:
                try:
                    url = att.get('payload', {}).get('url')
                    if not url: continue
                    name = att.get('payload', {}).get('filename') or att.get('name') or "file"
                    ext = os.path.splitext(name)[1].lower() or ".bin"
                    
                    att_type = att.get('type', '')
                    is_voice = (att_type in ['audio', 'voice'])
                    if is_voice and ext not in ['.m4a', '.mp3', '.ogg']: 
                        ext = ".m4a"
                    elif att_type == 'image' and ext in ['.bin', '']:
                        ext = ".jpg"
                    elif att_type == 'video' and ext in ['.bin', '']:
                        ext = ".mp4"

                    async with self.session.get(url, timeout=60) as r:
                        if r.status == 200:
                            content_type = r.headers.get('Content-Type', '')
                            if ext == ".bin":
                                import mimetypes
                                guessed = mimetypes.guess_extension(content_type)
                                if guessed: ext = guessed
                                
                            data = await r.read()
                            base_dir = os.path.dirname(os.path.abspath(__file__))
                            temp_media_dir = os.path.join(base_dir, "temp_media")
                            os.makedirs(temp_media_dir, exist_ok=True)
                            import time, random
                            tmp_p = os.path.join(temp_media_dir, f"att_{int(time.time())}_{random.randint(0,1000)}{ext}")
                            with open(tmp_p, "wb") as f:
                                f.write(data)
                            
                            if is_voice:
                                # Ensure message_text is not None so it doesn't trigger "Empty message" guardrail
                                if not message_text: message_text = "🎙️ (Voice message)"
                                
                                # Transcribe for ALL targets to ensure reliability
                                try:
                                    wav = tmp_p + ".wav"
                                    # Absolute path to the known working system ffmpeg
                                    ffmpeg_cmd = r"C:\Users\YourPC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.WinGet.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
                                    
                                    if not os.path.exists(tmp_p):
                                        log_error("MESSENGER_FFMPEG_PRE", f"Input file missing: {tmp_p}")
                                        message_text = (message_text or "") + "\n🎙️ [VOICE]: (Internal error: Audio file not found)"
                                        continue

                                    p = await asyncio.create_subprocess_exec(ffmpeg_cmd, "-y", "-i", tmp_p, "-ac", "1", "-ar", "16000", wav, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                                    _, stderr = await asyncio.wait_for(p.communicate(), timeout=30)
                                    
                                    if os.path.exists(wav):
                                        def trans(f):
                                            model = get_whisper_model()
                                            segs, _ = model.transcribe(f, beam_size=5)
                                            return " ".join([s.text.strip() for s in segs if s.text])
                                        txt = await asyncio.to_thread(trans, wav)
                                        if txt:
                                            message_text = (message_text or "") + f"\n🎙️ [VOICE TRANSCRIPT]: \"{txt}\""
                                        else:
                                            # Fallback if whisper returns nothing (silence or noise)
                                            message_text = (message_text or "") + "\n🎙️ [VOICE]: (Audio detected but no speech recognized)"
                                        os.remove(wav)
                                    else:
                                        # Fallback if ffmpeg fails
                                        err_msg = stderr.decode().strip() if stderr else "No stderr"
                                        log_error("MESSENGER_FFMPEG_FAIL", f"FFmpeg failed: {err_msg}")
                                        message_text = (message_text or "") + "\n🎙️ [VOICE]: (Audio file received but could not be processed)"
                                except Exception as e:
                                    log_error("MESSENGER_TRANSCRIPTION_ERROR", e)
                                    message_text = (message_text or "") + "\n🎙️ [VOICE]: (Internal transcription error)"

                                # Clean up the original audio file after transcription
                                if os.path.exists(tmp_p): os.remove(tmp_p)
                                tmp_p = None

                            if tmp_p: file_paths.append(tmp_p)
                except Exception as e: log_error("MESSENGER_ATT", e)

        if not message_text:
            if file_paths:
                message_text = "Please analyze these attachments."
            elif attachments:
                # Catch-all for voice/audio that failed or yielded no transcript
                message_text = "🎙️ (Voice/Media message received)"

        # ── Messenger Lightweight HUD ──
        # Facebook does NOT allow pages to delete messages without restricted permissions.
        # Instead of sending undeletable status messages, we use:
        #   1. A reaction emoji on the user's message (instant acknowledgment)
        #   2. A persistent typing indicator (refreshed every 4s)
        #   3. The Telegram standalone HUD for detailed monitoring
        import time as _time

        await self._send_sender_action(sender_id, "typing_on")

        # ── Typing Keepalive Task ──
        _hud_done = asyncio.Event()

        async def _typing_keepalive():
            """Refreshes the Messenger typing indicator every 4 seconds."""
            while not _hud_done.is_set():
                try:
                    await self._send_sender_action(sender_id, "typing_on")
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(_hud_done.wait(), timeout=4.0)
                    break
                except asyncio.TimeoutError:
                    pass

        typing_task = asyncio.create_task(_typing_keepalive())

        # ── Cross-Platform Notification (Telegram HUD) ──
        telegram_on_partial = None
        if self.core.telegram_bot:
            from config import ALLOWED_TELEGRAM_USERS
            for owner_id in ALLOWED_TELEGRAM_USERS:
                telegram_on_partial = await self.core.telegram_bot.create_standalone_hud(str(owner_id), "Messenger", target)
                break

        try:
            res_bundle = await self.core.process_request(
                user_id=sender_id,
                message=message_text,
                target=target,
                source="Messenger",
                file_paths=file_paths,
                on_partial=telegram_on_partial,
                generate_voice=self.router.get_voice_mode(sender_id),
                voice_name=self.router.get_voice(sender_id),
                chrome_profile=self.router.get_profile(sender_id) or ""
            )
            for f in file_paths:
                if os.path.exists(f): os.remove(f)

            # Signal completion
            _hud_done.set()
            if telegram_on_partial:
                await telegram_on_partial("__DONE__")

            # Dispatch final response — clean chat, no HUD clutter
            await self.adapter.deliver_response(sender_id, res_bundle)

        except Exception as e:
            log_error("MESSENGER_CORE", e)
            _hud_done.set()
            await self._send_messenger_message(sender_id, f"❌ Pipeline Error: {str(e)[:200]}")


    async def _handle_command(self, sender_id: str, cmd: str) -> None:
        from config import ALLOWED_MESSENGER_USERS
        if ALLOWED_MESSENGER_USERS and sender_id not in ALLOWED_MESSENGER_USERS:
            await self._send_messenger_message(sender_id, "⛔ Access Denied: Sorry, you are not an admin.")
            return

        handled = await self.router.dispatch_command(
            cmd=cmd,
            adapter=self.adapter,
            recipient_id=sender_id,
            user_name="User"
        )
        if not handled:
            await self._send_messenger_message(sender_id, f"❓ Unknown command.")

    def _humanize_response(self, text: str) -> str:
        """Convert rigid document-style AI output into clean, mobile-friendly Messenger format."""
        if not text: return ""
        log_event("MESSENGER", f"Humanizing input: {len(text)} chars")
        # ── Markdown formatting to Unicode for Perfect Design ──
        def to_bold(match):
            t = match.group(1)
            return ''.join(chr(ord(c)-ord('A')+0x1D5D4) if 'A'<=c<='Z' else chr(ord(c)-ord('a')+0x1D5EE) if 'a'<=c<='z' else chr(ord(c)-ord('0')+0x1D7E2) if '0'<=c<='9' else c for c in t)
            
        def to_italic(match):
            t = match.group(1)
            return ''.join(chr(ord(c)-ord('A')+0x1D608) if 'A'<=c<='Z' else chr(ord(c)-ord('a')+0x1D622) if 'a'<=c<='z' else c for c in t)
            
        text = re.sub(r'\*\*(?!\s)([^\n]+?)(?<!\s)\*\*', to_bold, text)
        text = re.sub(r'(?<![\w])__(?!\s)([^\n]+?)(?<!\s)__(?![\w])', to_bold, text)
        text = re.sub(r'\*(?!\s)([^\n\*]+?)(?<!\s)\*', to_italic, text)
        text = re.sub(r'_(?!\s)([^\n_]+?)(?<!\s)_', to_italic, text)

        # ── Pre-clean raw text ──
        text = re.sub(r'^[-─═━_]{3,}$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n\s*\.\s*\n', '\n', text)     # Remove lone period lines
        text = re.sub(r'\.\s*\n(?=[a-z])', '. ', text)  # Merge paragraph continuations

        # ── Strip closing questions — ONLY if there are other lines ──
        lines = text.split('\n')
        if len([l for l in lines if l.strip()]) > 1:
            text = re.sub(r'^(?:Ano|Anong|How|What|Paano)\s.*(?:assist|help|kailangan|tulong|ngayon).*\??\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
            lines = text.split('\n') # Refresh lines after potential strip
        result = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped == '.':
                # Only add blank line if last item wasn't already blank AND isn't a bullet
                if result and result[-1] != '' and not result[-1].startswith('•'):
                    result.append('')
                continue
            
            # ── SKIP section headers (waste mobile space) ──
            # Markdown headers (### Title)
            if re.match(r'^#{1,4}\s+', stripped):
                continue
            # ALL-CAPS headers (like "CONCEPCION UNO", "CORE IDENTITY")
            # Guard: require actual ASCII uppercase letters — Unicode bold chars satisfy
            # s == s.upper() trivially, so we must check for real ASCII A-Z presence.
            ascii_upper_count = sum(1 for c in stripped if 'A' <= c <= 'Z')
            if (ascii_upper_count >= 3
                    and stripped == stripped.upper()
                    and len(stripped) > 3
                    and len(stripped.split()) <= 8):
                if not any(c in stripped for c in ['→', '.', ',', '!', '?']):
                    continue
            # Title Case headers — ONLY multi-word clean titles with no commas/apostrophes/periods
            # Requires 2+ words to avoid stripping single-word data items (folder names, filenames, etc.)
            # Only check words that start with ASCII letters (not Unicode bold)
            if len(stripped) < 40 and not any(c in stripped for c in ['.', ',', '!', '?', "'", '"', '→', '•', ':', '_', '-']):
                words = stripped.split()
                if 2 <= len(words) <= 4:
                    cap_words = [w for w in words if ('A' <= w[0] <= 'Z') or w.lower() in ('&', 'and', 'of', 'the', 'in', 'for', 'ng', 'sa', 'at', 'mga')]
                    if len(cap_words) == len(words):  # ALL words must be capitalized or connectors
                        continue

            # ── Pre-process line for inline arrows (squashed lists) ──
            # If the line contains inline arrows, we process them into segments first
            if ' → ' in stripped:
                # Remove leading bullet/arrow just for the split logic
                clean_stripped = re.sub(r'^[*→•\-]\s*', '', stripped)
                parts = clean_stripped.split(' → ')
                
                # If it looks like a "Label: Content" pattern (exactly 2 parts, first part very short)
                if len(parts) == 2 and len(parts[0].split()) <= 4:
                    label = parts[0].strip().rstrip(':')
                    content = parts[1].strip().rstrip('.')
                    result.append(f'• {label}: {content}')
                else:
                    # Otherwise it's a squashed bullet list
                    for seg in parts:
                        seg = seg.strip().rstrip('.')
                        if seg:
                            result.append(f'• {seg}')
                continue
                
            # ── Normal Bullets (no inline arrows) ──
            arrow_match = re.match(r'^[*→•\-]\s*(.+)', stripped)
            if arrow_match:
                content = arrow_match.group(1).strip().rstrip('.,').strip()
                result.append(f'• {content}')
                continue
            
            # Normal text — always pass through
            if stripped:
                result.append(stripped)
        
        # ── Final assembly ──
        output = '\n'.join(result).strip()
        # Collapse 3+ blank lines to single blank line
        output = re.sub(r'\n{3,}', '\n\n', output)
        # Ensure perfect spacing: force exactly one blank line between bullets for an elegant look
        # This replaces cramped/squashed bullets with properly spaced items
        output = re.sub(r'(•[^\n]+)\n(?=•)', r'\1\n\n', output)
        output = output.rstrip()
        
        log_event("MESSENGER", f"Humanization complete: {len(output)} chars")
        return output

    async def start_webhook_server(self) -> None:
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50, keepalive_timeout=30, enable_cleanup_closed=True),
            connector_owner=False
        )
        app = web.Application()

        async def get_handler(request):
            if request.query.get('hub.verify_token') == MESSENGER_VERIFY_TOKEN: 
                return web.Response(text=request.query.get('hub.challenge'))
            
            # Return a Premium Status Page for manual browser visits
            html = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>BANE NLP | System Status</title>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
                <style>
                    :root {
                        --bg: #0a0a0c;
                        --card: #16161a;
                        --accent: #6366f1;
                        --text: #e2e8f0;
                    }
                    body {
                        margin: 0;
                        padding: 0;
                        font-family: 'Outfit', sans-serif;
                        background: var(--bg);
                        color: var(--text);
                        height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        overflow: hidden;
                    }
                    .container {
                        text-align: center;
                        background: var(--card);
                        padding: 3rem;
                        border-radius: 24px;
                        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                        border: 1px solid rgba(255,255,255,0.05);
                        max-width: 400px;
                        width: 90%;
                        position: relative;
                        animation: fadeIn 0.8s ease-out;
                    }
                    @keyframes fadeIn {
                        from { opacity: 0; transform: translateY(20px); }
                        to { opacity: 1; transform: translateY(0); }
                    }
                    .logo {
                        font-size: 2.5rem;
                        font-weight: 600;
                        letter-spacing: -1px;
                        margin-bottom: 0.5rem;
                        background: linear-gradient(135deg, #818cf8, #c084fc);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                    }
                    .status-badge {
                        display: inline-flex;
                        align-items: center;
                        background: rgba(34, 197, 94, 0.1);
                        color: #4ade80;
                        padding: 0.5rem 1rem;
                        border-radius: 99px;
                        font-size: 0.875rem;
                        font-weight: 600;
                        margin-bottom: 2rem;
                    }
                    .status-dot {
                        width: 8px;
                        height: 8px;
                        background: #22c55e;
                        border-radius: 50%;
                        margin-right: 8px;
                        box-shadow: 0 0 10px #22c55e;
                        animation: pulse 2s infinite;
                    }
                    @keyframes pulse {
                        0% { opacity: 1; }
                        50% { opacity: 0.5; }
                        100% { opacity: 1; }
                    }
                    .info {
                        color: #94a3b8;
                        font-size: 0.95rem;
                        line-height: 1.6;
                    }
                    .divider {
                        height: 1px;
                        background: rgba(255,255,255,0.05);
                        margin: 2rem 0;
                    }
                    footer {
                        font-size: 0.75rem;
                        color: #475569;
                        margin-top: 1rem;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">BANE NLP</div>
                    <div class="status-badge">
                        <div class="status-dot"></div>
                        WEBHOOK ACTIVE
                    </div>
                    <div class="info">
                        The secure messenger bridge is online and standing by. 
                        Targeting <b>Gemini & NotebookLM</b>.
                    </div>
                    <div class="divider"></div>
                    <div class="info" style="font-size: 0.8rem;">
                        Endpoint: <code>/webhooks/messenger</code>
                    </div>
                    <footer>© 2026 JAYSON COMBATE</footer>
                </div>
            </body>
            </html>
            """
            return web.Response(text=html, content_type='text/html')

        async def post_handler(request):
            try:
                data = await request.json()
            except Exception:
                return web.Response(status=400)
                
            log_event("MESSENGER_WEBHOOK", f"Received data: {json.dumps(data)}")
            if data and data.get('object') == 'page':
                for e in data.get('entry', []):
                    for m in e.get('messaging', []):
                        sid = m.get('sender', {}).get('id')
                        if not sid: continue
                        md = m.get('message', {})
                        mid = md.get('mid')
                        if mid:
                            if mid in self._processed_mids: return web.Response(text='EVENT_RECEIVED')
                            self._processed_mids.add(mid)

                        # Handle Quick Replies
                        if md.get('quick_reply'):
                            p = md['quick_reply'].get('payload')
                            if p:
                                # Convert messenger payload format to the router's format
                                if p.startswith("SET_TARGET_"):
                                    p = f"switch_target:{p.replace('SET_TARGET_', '')}"
                                elif p.startswith("SET_VOICE_"):
                                    p = f"switch_voice:{p.replace('SET_VOICE_', '')}"
                                elif p.startswith("MENU_GEMINI_"):
                                    p = f"gemini_launch_menu:{p.replace('MENU_GEMINI_', '').lower()}"
                                elif p.startswith("LAUNCH_CHROME:"):
                                    p = p.lower()
                                
                                handled = await self.router.handle_callback(p, sid, self.adapter, sid, message_ref=None)
                                if not handled:
                                    # Fallback if it's not a router callback (e.g. suggestions)
                                    asyncio.create_task(self._process_async(sid, p, message_mid=mid))
                                return web.Response(text='EVENT_RECEIVED')

                        txt = md.get('text')
                        atts = md.get('attachments', [])
                        if txt or atts:
                            asyncio.create_task(self._process_async(sid, str(txt or ""), attachments=atts, message_mid=mid))
            return web.Response(text='EVENT_RECEIVED')

        async def portfolio_query_handler(request):
            try:
                data = await request.json()
                query = data.get("query")
                if not query:
                    return web.json_response({"error": "Empty query"}, status=400)
                
                log_event("PORTFOLIO_API", f"Received query: {query[:100]}...")
                
                # ── Cross-Platform Notification (Telegram HUD) ──
                on_partial = None
                if self.core.telegram_bot:
                    from config import ALLOWED_TELEGRAM_USERS
                    for owner_id in ALLOWED_TELEGRAM_USERS:
                        on_partial = await self.core.telegram_bot.create_standalone_hud(str(owner_id), "Portfolio", "gemini")
                        break

                # Process the request synchronously through the 7 layers
                res_bundle = await self.core.process_request(
                    user_id="PORTFOLIO",
                    message=query,
                    target="gemini_portfolio",
                    source="Portfolio",
                    on_partial=on_partial,
                    generate_voice=False
                )
                
                # Signal HUD completion
                if on_partial: await on_partial("__DONE__")
                
                if isinstance(res_bundle, dict):
                    text = res_bundle.get("text", "")
                    return web.json_response({"text": text})
                else:
                    return web.json_response({"text": str(res_bundle)})
            except Exception as e:
                log_error("PORTFOLIO_API_ERROR", e)
                return web.json_response({"error": str(e)}, status=500)

        async def portfolio_tts_handler(request):
            try:
                from config import DEFAULT_VOICE
                data = await request.json()
                text = data.get("text", "")
                voice = data.get("voice", DEFAULT_VOICE)
                
                if not text:
                    return web.json_response({"error": "Empty text"}, status=400)
                
                from services.voice_engine import VoiceEngine
                engine = VoiceEngine(voice_name=voice)
                
                # Use the professional engine used by BANE bots
                # generate_speech normally returns OGG, but for the web API, 
                # we want MP3 for maximum mobile compatibility (iOS/Safari).
                import tempfile
                temp_mp3 = tempfile.mktemp(suffix=".mp3")
                
                from services.voice_engine import VoiceEngine
                engine = VoiceEngine(voice_name=voice)
                
                # We'll use edge_tts directly here to get the MP3 version
                import edge_tts
                target_cfg = engine.config # Uses the tuned pitch/rate from config
                communicate = edge_tts.Communicate(
                    text=engine._clean_for_speech(text), 
                    voice=target_cfg['voice'],
                    rate=target_cfg['rate'],
                    pitch=target_cfg['pitch']
                )
                await communicate.save(temp_mp3)

                if os.path.exists(temp_mp3):
                    with open(temp_mp3, "rb") as f:
                        content = f.read()
                    
                    # Cleanup
                    try: os.remove(temp_mp3)
                    except: pass
                    
                    return web.Response(body=content, content_type="audio/mpeg")
                else:
                    return web.json_response({"error": "TTS failed"}, status=500)
            except Exception as e:
                log_error("PORTFOLIO_TTS_ERROR", e)
                return web.json_response({"error": str(e)}, status=500)

        # ── Dashboard API Endpoints ─────────────────────────────────────────────
        from core.logger import (
            dashboard_subscribe, dashboard_unsubscribe,
            dashboard_get_state, dashboard_get_recent_events
        )

        async def dashboard_events_handler(request):
            """SSE endpoint for real-time dashboard event streaming."""
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*',
                }
            )
            await response.prepare(request)

            q = dashboard_subscribe()
            try:
                # Send recent events as initial burst
                recent = dashboard_get_recent_events(50)
                for evt in recent:
                    data = json.dumps(evt)
                    await response.write(f"data: {data}\n\n".encode('utf-8'))

                # Stream new events
                while True:
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=15.0)
                        data = json.dumps(evt)
                        await response.write(f"data: {data}\n\n".encode('utf-8'))
                    except asyncio.TimeoutError:
                        # Send keepalive ping
                        await response.write(b": keepalive\n\n")
                    except (ConnectionResetError, ConnectionAbortedError):
                        break
            finally:
                dashboard_unsubscribe(q)
            return response

        async def dashboard_status_handler(request):
            """Return current pipeline state as JSON."""
            state = dashboard_get_state()
            return web.json_response(state, headers={
                'Access-Control-Allow-Origin': '*',
            })

        async def dashboard_kill_handler(request):
            """Kill the current active pipeline process."""
            log_event("DASHBOARD", "⚠️ Kill switch activated from Dashboard!")
            # Set the kill flag that the engine checks
            if hasattr(self.core, '_kill_active'):
                self.core._kill_active = True
            return web.json_response(
                {"status": "kill_signal_sent"},
                headers={'Access-Control-Allow-Origin': '*'}
            )

        async def dashboard_restart_handler(request):
            """Restart the BANE-NLP system."""
            log_event("DASHBOARD", "🔄 System restart triggered from Dashboard!")
            # Schedule restart after response is sent
            async def _delayed_restart():
                await asyncio.sleep(1)
                import sys
                os.execv(sys.executable, [sys.executable] + sys.argv)
            asyncio.create_task(_delayed_restart())
            return web.json_response(
                {"status": "restart_scheduled"},
                headers={'Access-Control-Allow-Origin': '*'}
            )

        app.router.add_get('/webhooks/messenger', get_handler)
        app.router.add_post('/webhooks/messenger', post_handler)
        app.router.add_post('/api/portfolio_query', portfolio_query_handler)
        app.router.add_post('/api/tts', portfolio_tts_handler)
        app.router.add_get('/api/dashboard/events', dashboard_events_handler)
        app.router.add_get('/api/dashboard/status', dashboard_status_handler)
        app.router.add_post('/api/dashboard/kill', dashboard_kill_handler)
        app.router.add_post('/api/dashboard/restart', dashboard_restart_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', MESSENGER_WEBHOOK_PORT)
        await site.start()
        log_event("STARTUP", f"Messenger Webhook running asynchronously on port {MESSENGER_WEBHOOK_PORT}")

    def start(self): 
        asyncio.create_task(self.start_webhook_server())
