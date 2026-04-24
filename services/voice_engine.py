import edge_tts
import os
import shutil
import tempfile
import asyncio
import re
from core.logger import log_event, log_error
from config import VOICE_MODELS, DEFAULT_VOICE

class VoiceEngine:
    """Surgical TTS Engine for BANE NLP — Enhanced with Multi-Model Human Pitch Mixer."""

    def __init__(self, voice_name=DEFAULT_VOICE):
        self.current_voice_name = voice_name
        self.config = VOICE_MODELS.get(voice_name, VOICE_MODELS[DEFAULT_VOICE])

    def set_voice(self, voice_name: str):
        """Switch the active voice model."""
        if voice_name in VOICE_MODELS:
            self.current_voice_name = voice_name
            self.config = VOICE_MODELS[voice_name]
            log_event("VOICE", f"Active voice switched to: {voice_name}")

    def detect_language(self, text: str) -> str:
        """
        Detects if text is primarily Filipino/Tagalog or English.
        Returns 'fil' or 'en'.
        """
        # Common Tagalog/Taglish keywords - Removed ambiguous "at", "in", "to" type overlaps
        tagalog_keywords = [
            "ako", "ikaw", "siya", "tayo", "kami", "sila", "ito", "iyan", "iyon", 
            "ang", "mga", "ng", "sa", "ay", "na", "ba", "po", "opo", "nga",
            "hindi", "wala", "meron", "kumusta", "salamat", "isang", "dahil",
            "kasi", "pero", "tapos", "tsaka", "natin", "ninyo", "kanila",
            "may", "lahat", "rin", "din", "lang", "kahit", "saan", "kailan", 
            "ano", "bakit", "paano", "maganda", "mabuti", "masaya", "gusto",
            "alam", "kita", "namin", "mo", "ka"
        ]
        
        text_lower = text.lower()
        # Count unique Tagalog keywords found
        found_words = [word for word in tagalog_keywords if re.search(rf'\b{word}\b', text_lower)]
        
        # SENSITIVITY CALIBRATION:
        # We need more than a few words to trigger a full language switch.
        # This prevents accidental English "at", "in", "sa" (South Africa/etc) from triggering it.
        if len(found_words) >= 3:
            return "fil"
        return "en"

    async def generate_speech(self, text: str, override_voice_name: str | None = None) -> str | None:
        """
        Convert text to speech and return the local path of the generated OGG.
        Automatically switches to an appropriate voice if auto-detection is enabled.
        """
        if not text:
            return None

        # Clean text for TTS (strip markdown artifacts)
        clean_text = self._clean_for_speech(text)
        if len(clean_text) < 2:
            return None

        # Resolve voice configuration for this specific call
        target_name = override_voice_name or self.current_voice_name
        target_cfg = VOICE_MODELS.get(target_name, VOICE_MODELS[DEFAULT_VOICE])

        # Automatic Language Routing
        lang = self.detect_language(clean_text)
        
        active_voice = target_cfg['voice']
        active_pitch = target_cfg['pitch']
        active_rate = target_cfg['rate']
        active_vibration = target_cfg.get('vibration', False)
        
        # Override if language mismatch (Surgical Routing)
        is_current_fil = "fil-PH" in active_voice
        if lang == "fil" and not is_current_fil:
            # Switch to default Filipino for this response (Gender aware fallback)
            # If user chose a female voice, try to use a female Filipino voice
            if "jenny" in active_voice.lower() or "aria" in active_voice.lower() or "blessica" in active_voice.lower():
                fil_cfg = VOICE_MODELS.get("Filipino (Blessica)", VOICE_MODELS["Filipino (Angelo)"])
            else:
                fil_cfg = VOICE_MODELS["Filipino (Angelo)"]
            active_voice = fil_cfg['voice']
            active_pitch = fil_cfg['pitch']
            active_rate = fil_cfg['rate']
            active_vibration = fil_cfg.get('vibration', False)
            log_event("VOICE", f"Auto-routed to Filipino ({active_voice}) for Taglish content.")
        elif lang == "en" and is_current_fil:
            # Switch to default English for this response (Gender aware fallback)
            if "blessica" in active_voice.lower() or "jenny" in active_voice.lower():
                en_cfg = VOICE_MODELS.get("English (Jenny)", VOICE_MODELS["Bane Professional V2.0"])
            else:
                en_cfg = VOICE_MODELS["Bane Professional V2.0"]
            active_voice = en_cfg['voice']
            active_pitch = en_cfg['pitch']
            active_rate = en_cfg['rate']
            active_vibration = en_cfg.get('vibration', False)
            log_event("VOICE", f"Auto-routed to English ({active_voice}) for pure English content.")

        temp_mp3 = tempfile.mktemp(suffix=".mp3")
        temp_ogg = tempfile.mktemp(suffix=".ogg")
        try:
            communicate = edge_tts.Communicate(
                text=clean_text, 
                voice=active_voice,
                rate=active_rate,
                pitch=active_pitch
            )
            await communicate.save(temp_mp3)
            
            # Convert MP3 to OPUS-encoded OGG for Telegram Voice Note compatibility
            # Resolve FFmpeg: WinGet install → system PATH → local copy
            _WINGET_FFMPEG = (
                r"C:\Users\YourPC\AppData\Local\Microsoft\WinGet\Packages"
                r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
                r"\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
            )
            ffmpeg_path = (
                (_WINGET_FFMPEG if os.path.isfile(_WINGET_FFMPEG) else None)
                or shutil.which('ffmpeg')
                or os.path.join(os.path.dirname(__file__), 'ffmpeg.exe')
            )
            
            # Convert MP3 to OPUS-encoded OGG for Telegram Voice Note compatibility
            # Optimized for speed and small file size (faster upload)
            ffmpeg_args = [
                ffmpeg_path, '-y', '-i', temp_mp3,
                '-c:a', 'libopus',
                '-b:a', '24k',        # Lower bitrate (24k is plenty for clear speech)
                '-ac', '1',           # Mono (saves space)
                '-application', 'voip', # Optimized for human speech
                '-threads', '0'       # Use all available cores
            ]
            
            if active_vibration:
                # Add bass boost for resonance and a very subtle vibrato for literal 'vibration' tone
                ffmpeg_args.extend(['-af', 'bass=g=5:f=110,vibrato=f=4.0:d=0.25'])
            
            ffmpeg_args.append(temp_ogg)
            
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_args,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            
            if proc.returncode != 0:
                raise Exception(f"ffmpeg conversion failed with exit code {proc.returncode}")
            
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
                
            log_event("VOICE", f"Speech generated ({active_voice}) for {len(clean_text)} chars: {temp_ogg}")
            return temp_ogg
        except Exception as e:
            log_error("VOICE", f"Speech generation error: {e}")
            if os.path.exists(temp_mp3): os.remove(temp_mp3)
            if os.path.exists(temp_ogg): os.remove(temp_ogg)
            return None

    def _clean_for_speech(self, text: str) -> str:
        """Strip markdown and robot-only symbols before spoken generation."""
        # Remove bold/italic markers
        t = re.sub(r'[*_#]', '', text)
        # Remove arrow symbols
        t = re.sub(r'[→•\-\d\.]+\s', ' ', t)
        # Remove horizontal lines
        t = re.sub(r'[-=]{3,}', '', t)
        # Remove URLS
        t = re.sub(r'https?://\S+', 'link', t)
        # Remove tool call JSON (safety)
        t = re.sub(r'```json[\s\S]*?```', '', t)
        # Remove [L#] markers
        t = re.sub(r'\[L\d+(\.\d+)?\]', '', t)
        return t.strip()
