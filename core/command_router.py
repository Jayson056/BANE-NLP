"""
Command Router — Unified Business Logic for All Platforms
==========================================================
Extracted from telegram_bot.py and messenger_bot.py.

All /commands and button callbacks route through here.
The router calls ChannelAdapter methods to send responses,
keeping platform-specific details out of the business logic.

Adding a new command? Add it HERE once — it works on all platforms.
"""

import os
import re
import time
import subprocess
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from config import (
    DEFAULT_TARGET, TARGETS, CHROME_PROFILES,
    MASTER_PROFILES, PROFILE_PASSWORD,
    VOICE_MODELS, DEFAULT_VOICE, CHROME_PATH
)
from core.logger import log_event, log_error


class CommandRouter:
    """Shared command handler for all communication platforms."""

    def __init__(self, bane_core):
        self.core = bane_core
        # Per-user state (keyed by str(user_id))
        self._user_targets: Dict[str, str] = {}
        self._user_profiles: Dict[str, str] = {}
        self._user_voices: Dict[str, str] = {}
        self._user_voice_mode: Dict[str, bool] = {}
        # Master profile sessions {user_id: {"profile", "target", "expires"}}
        self._master_sessions: Dict[str, Dict[str, Any]] = {}
        # Pending password verification {user_id: {"profile", "target", "ts"}}
        self._pending_password: Dict[str, Dict[str, Any]] = {}

    # ══════════════════════════════════════════════════════════════════════
    # State Accessors
    # ══════════════════════════════════════════════════════════════════════

    def get_target(self, user_id: str) -> str:
        return self._user_targets.get(user_id, DEFAULT_TARGET)

    def set_target(self, user_id: str, target: str):
        self._user_targets[user_id] = target

    def get_voice(self, user_id: str) -> str:
        return self._user_voices.get(user_id, DEFAULT_VOICE)

    def set_voice(self, user_id: str, voice: str):
        self._user_voices[user_id] = voice

    def get_voice_mode(self, user_id: str) -> bool:
        return self._user_voice_mode.get(user_id, False)

    def toggle_voice_mode(self, user_id: str) -> bool:
        new_state = not self._user_voice_mode.get(user_id, False)
        self._user_voice_mode[user_id] = new_state
        return new_state

    def get_profile(self, user_id: str) -> Optional[str]:
        return self._user_profiles.get(user_id)

    def set_profile(self, user_id: str, profile: str):
        self._user_profiles[user_id] = profile

    # ══════════════════════════════════════════════════════════════════════
    # Commands
    # ══════════════════════════════════════════════════════════════════════

    async def cmd_start(self, adapter, recipient_id: str, user_name: str = "User"):
        text = (
            f"⚡ <b>BANE-V4: Autonomous Pipeline Active</b>\n\n"
            f"Hello {user_name}! I am BANE, Jayson's technical assistant.\n"
            f"Current default target: <code>{DEFAULT_TARGET.upper()}</code>\n\n"
            "Type /help to see all available commands and guides."
        )
        await adapter.send_text(recipient_id, text, parse_mode="HTML")

    async def cmd_help(self, adapter, recipient_id: str):
        text = (
            "📖 <b>BANE Command Reference</b>\n\n"
            "⚙️ <b>System Commands:</b>\n"
            "• <code>/status</code> : System connectivity & stats\n"
            "• <code>/target</code> : Choose Gemini, ChatGPT, or NotebookLM\n"
            "• <code>/new</code> : Fresh chat (clears browser context)\n"
            "• <code>/voice</code> : Toggle voice reply on/off\n"
            "• <code>/terminate</code> : Force stop current AI loop\n"
            "• <code>/restart</code> : Reboot the entire pipeline\n\n"
            "🌐 <b>Browser Launchers:</b>\n"
            "• <code>/gemini</code> : Open Gemini in Chrome\n"
            "• <code>/chatgpt</code> : Open ChatGPT in Chrome\n"
            "• <code>/notebooklm</code> : Open NotebookLM in Chrome\n"
            "• <code>/activechrome</code> : List running profiles\n"
            "• <code>/closechrome</code> : Force close all Chrome\n"
            "• <code>/delegate</code> : Force spawn a background worker\n\n"
            "💡 <b>Tips:</b>\n"
            "• Prefix with @gemini, @chatgpt, or @notebooklm to override target.\n"
            "• Attach files, photos, or voice messages to pass them to the AI."
        )
        await adapter.send_text(recipient_id, text, parse_mode="HTML")

    async def cmd_status(self, adapter, recipient_id: str):
        from core.system_stats import get_machine_report
        stats = get_machine_report()
        user_id = recipient_id
        target = self.get_target(user_id)
        voice_on = "ON" if self.get_voice_mode(user_id) else "OFF"

        text = (
            "✅ <b>BANE-V4 System Status</b>\n\n"
            "🖥️ <b>Host Machine:</b>\n"
            f"• CPU Load: <code>{stats['cpu']}%</code>\n"
            f"• Memory Load: <code>{stats['ram']}%</code>\n"
            f"• Disk Space: <code>{stats['disk']}</code>\n"
            f"• Uptime: <code>{stats['uptime']}</code>\n\n"
            "🧠 <b>AI Pipeline:</b>\n"
            f"• Default Engine: <code>{target.upper()}</code>\n"
            "• Bridge Protocol: <code>Connected & Listening</code>\n"
            f"• MCP Registry: <code>{stats['tools']} Tools Loaded</code>\n"
            f"• Voice Mode: <code>{voice_on}</code>\n\n"
            "🌐 <b>Deployment:</b>\n"
            "• Domain: <code>jayson056.space</code>\n"
            "• Tunnel: <code>bane</code>"
        )
        await adapter.send_text(recipient_id, text, parse_mode="HTML")

    async def cmd_new(self, adapter, recipient_id: str):
        await adapter.send_typing(recipient_id)
        await self.core.new_conversation()
        await adapter.send_text(recipient_id, "🆕 <b>New conversation context initialized.</b>", parse_mode="HTML")

    async def cmd_target(self, adapter, recipient_id: str):
        buttons = [
            {"label": "🔵 Gemini", "data": "switch_target:gemini"},
            {"label": "🟢 ChatGPT", "data": "switch_target:chatgpt"},
            {"label": "🧠 NotebookLM", "data": "switch_target:notebooklm"},
        ]
        await adapter.send_buttons(recipient_id, "🎯 <b>Select Target Engine:</b>", buttons, parse_mode="HTML")

    async def cmd_voice(self, adapter, recipient_id: str):
        user_id = recipient_id
        new_state = self.toggle_voice_mode(user_id)
        status = "ON 🎙️" if new_state else "OFF 🔇"

        buttons = []
        for name, cfg in VOICE_MODELS.items():
            icon = "🇵🇭" if "fil-PH" in cfg['voice'] else "🇺🇸" if "en-US" in cfg['voice'] else "🇬🇧"
            buttons.append({"label": f"{icon} {name}", "data": f"switch_voice:{name}"})

        text = (
            f"🎙️ <b>Voice Mode: {status}</b>\n\n"
            "When ON, I reply with text + professional voice message.\n"
            f"Current Model: <code>{self.get_voice(user_id)}</code>\n\n"
            "<b>Choose a Professional Model:</b>"
        )
        await adapter.send_buttons(recipient_id, text, buttons, parse_mode="HTML")

    async def cmd_terminate(self, adapter, recipient_id: str):
        user_id = recipient_id
        self.core.cancel_tokens[user_id] = True
        await adapter.send_text(
            recipient_id,
            "🛑 <b>Process Terminated:</b> Current AI execution loop forcefully stopped.",
            parse_mode="HTML"
        )

    async def cmd_restart(self, adapter, recipient_id: str):
        import sys
        await adapter.send_text(recipient_id, "🔄 <b>Restarting Engine:</b> Performing an in-place reboot...", parse_mode="HTML")
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            await adapter.send_text(recipient_id, f"❌ Error on restart: {e}")

    async def cmd_closechrome(self, adapter, recipient_id: str):
        await adapter.send_text(recipient_id, "🛑 <b>Closing Chrome:</b> Terminating all Google Chrome processes...", parse_mode="HTML")
        try:
            subprocess.Popen('taskkill /F /IM chrome.exe /T', shell=True)
        except Exception as e:
            await adapter.send_text(recipient_id, f"❌ Error closing chrome: {e}")

    async def cmd_activechrome(self, adapter, recipient_id: str):
        import psutil
        active_profiles = []
        for proc in psutil.process_iter(['name', 'cmdline']):
            if proc.info['name'] == 'chrome.exe':
                cmdline = proc.info['cmdline']
                if cmdline:
                    for arg in cmdline:
                        if "--profile-directory=" in arg:
                            p_name = arg.split("=")[1]
                            if p_name not in active_profiles:
                                active_profiles.append(p_name)

        connected_engines = self.core.bridge.get_active_connections()
        lines = ["🌐 <b>Active Chrome Instances</b>", "────────────────────"]

        if not active_profiles:
            lines.append("🚫 No running Chrome profiles detected.")
        else:
            for p in active_profiles:
                label = CHROME_PROFILES.get(p, {}).get("label", f"Other ({p})")
                color = CHROME_PROFILES.get(p, {}).get("color", "⚪")
                status = "🟢 Connected" if p in connected_engines else "🟡 Standby"
                lines.append(f"{color} <b>{label}</b>: {status}")

        lines.append("────────────────────")
        lines.append(f"⏱ <b>Last Poll:</b> {datetime.now().strftime('%H:%M:%S')}")
        await adapter.send_text(recipient_id, "\n".join(lines), parse_mode="HTML")

    async def cmd_gemini(self, adapter, recipient_id: str):
        buttons = [
            {"label": "🌐 Gemini General", "data": "gemini_launch_menu:gemini_general"},
            {"label": "🤖 Gem-Bane_NLP", "data": "gemini_launch_menu:gemini_custom"},
            {"label": "💻 Gem-AppDev Review", "data": "gemini_launch_menu:gemini_appdev"},
        ]
        await adapter.send_buttons(recipient_id, "🔵 <b>Choose Gemini Model to Launch:</b>", buttons, parse_mode="HTML")

    async def cmd_chatgpt(self, adapter, recipient_id: str):
        await self.show_profile_picker(adapter, recipient_id, "chatgpt")

    async def cmd_notebooklm(self, adapter, recipient_id: str):
        await self.show_profile_picker(adapter, recipient_id, "notebooklm")

    async def cmd_delegate(self, adapter, recipient_id: str):
        """V2 Phase 3: Manually spawn a background worker for testing."""
        from pipeline.worker import EphemeralWorker, WorkerTask
        import asyncio
        
        await adapter.send_text(recipient_id, "🔄 <b>Delegation:</b> Spawning background worker...", parse_mode="HTML")
        
        # Test task
        task = WorkerTask(
            goal="Fetch the top 3 news headlines today using web_tools.",
            target_profile="Profile 8",
            target_llm="gemini",
            parent_request_id="manual_delegate",
            user_id=recipient_id,
            platform="telegram"
        )
        
        worker = EphemeralWorker(self.core.engine, timeout=60.0)
        
        # Run in background
        async def run_and_report():
            res = await worker.execute(task)
            status = "✅ Success" if res.success else "❌ Failed"
            await adapter.send_text(recipient_id, f"<b>Worker Result ({status}):</b>\n<pre>{res.text}</pre>", parse_mode="HTML")
            
        asyncio.create_task(run_and_report())

    def get_available_profiles(self) -> List[str]:
        """V2 Phase 3: Get Chrome profiles not currently in use by an active worker."""
        # For now, return a static list of background automation profiles.
        # Could be enhanced to dynamically check which ones are active.
        return ["Profile 8", "Profile 4", "Profile 3"]

    # ══════════════════════════════════════════════════════════════════════
    # Profile Picker & Chrome Launch
    # ══════════════════════════════════════════════════════════════════════

    async def show_profile_picker(self, adapter, recipient_id: str, target: str, message_ref: Any = None):
        label = TARGETS.get(target, {}).get("label", target.upper())
        buttons = []
        for pid, info in CHROME_PROFILES.items():
            badge = "🔐 " if pid in MASTER_PROFILES else ""
            buttons.append({
                "label": f"{badge}{info['color']} {info['label']}",
                "data": f"launch_chrome:{target}:{pid}"
            })
        
        # Add a back button if it's Gemini custom/general
        if target.startswith("gemini_"):
            buttons.append({"label": "⬅️ Back", "data": "switch_target:gemini"})

        text = (
            f"🌐 <b>Select Profile for {label}:</b>\n"
            "<i>🔐 = Password-protected Master Profile</i>"
        )
        
        if message_ref:
            await adapter.edit_message(recipient_id, message_ref, text, buttons, parse_mode="HTML")
        else:
            await adapter.send_buttons(recipient_id, text, buttons, parse_mode="HTML")

    async def launch_chrome_profile(self, adapter, recipient_id: str, user_id: str, target: str, profile: str):
        """Launch a Chrome profile for the given target. Returns True if launched."""
        url = TARGETS.get(target, {}).get("profiles", {}).get(profile)
        if not url:
            await adapter.send_text(recipient_id, f"❌ Error: No URL for profile <code>{profile}</code>", parse_mode="HTML")
            return False

        is_connected = self.core.bridge.is_profile_connected(profile, target)

        if not is_connected:
            from config import CHROME_USER_DATA_DIR, CHROME_EXTENSION_PATH, CHROME_PATH
            self.core.bridge.set_pending_profile(profile)
            sep = "&" if "?" in url else "?"
            final_url = f"{url}{sep}bnp_profile={profile.replace(' ', '+')}"
            
            # ── Robust Launcher with Extension Injection ──
            # We use a direct list-based Popen to avoid shell quoting issues
            cmd = [
                CHROME_PATH,
                f"--profile-directory={profile}",
                f"--user-data-dir={CHROME_USER_DATA_DIR}",
                f"--load-extension={CHROME_EXTENSION_PATH}",
                "--no-first-run",
                "--no-default-browser-check",
                final_url
            ]
            
            # Log the exact command for debugging
            log_event("ROUTER", f"Launching Chrome: {' '.join(cmd)}")
            subprocess.Popen(cmd)
            state_msg = "Launched (Force-Inject):"
        else:
            state_msg = "Connected:"

        self.set_profile(user_id, profile)
        self.set_target(user_id, target)

        p_label = CHROME_PROFILES.get(profile, {}).get("label", profile)
        t_label = TARGETS.get(target, {}).get("label", target.upper())
        await adapter.send_text(
            recipient_id,
            f"🚀 <b>{state_msg}</b> <code>{t_label}</code>\n"
            f"👤 <b>Profile:</b> <code>{p_label}</code>",
            parse_mode="HTML"
        )
        return True

    # ══════════════════════════════════════════════════════════════════════
    # Callback Handlers (button presses)
    # ══════════════════════════════════════════════════════════════════════

    async def handle_callback(self, callback_data: str, user_id: str, adapter, recipient_id: str, message_ref=None):
        """
        Route button callback data to the appropriate handler.
        
        Returns True if handled, False if the callback is platform-specific.
        """
        if callback_data.startswith("gemini_launch_menu:"):
            target = callback_data.split(":")[1]
            await self.show_profile_picker(adapter, recipient_id, target, message_ref=message_ref)
            return True

        if callback_data.startswith("switch_target:"):
            target = callback_data.split(":")[1]

            if target == "gemini":
                buttons = [
                    {"label": "🌐 Gemini General", "data": "switch_target:gemini_general"},
                    {"label": "🤖 Gem-Bane_NLP", "data": "switch_target:gemini_custom"},
                    {"label": "💻 Gem-AppDev Review", "data": "switch_target:gemini_appdev"},
                    {"label": "⬅️ Back", "data": "switch_target:back_to_main"},
                ]
                await adapter.edit_message(recipient_id, message_ref, "🔵 <b>Choose Gemini Model:</b>", buttons, parse_mode="HTML")
                return True

            if target == "back_to_main":
                buttons = [
                    {"label": "🔵 Gemini", "data": "switch_target:gemini"},
                    {"label": "🟢 ChatGPT", "data": "switch_target:chatgpt"},
                    {"label": "🧠 NotebookLM", "data": "switch_target:notebooklm"},
                ]
                await adapter.edit_message(recipient_id, message_ref, "🎯 <b>Select Target Engine:</b>", buttons, parse_mode="HTML")
                return True

            self.set_target(user_id, target)
            await self.core.switch_target(user_id, target)
            label = TARGETS.get(target, {}).get("label", target.upper())
            await adapter.edit_message(recipient_id, message_ref, f"✅ <b>Target Switched:</b> <code>{label}</code>", parse_mode="HTML")
            return True

        if callback_data.startswith("switch_voice:"):
            voice_name = callback_data.split(":")[1]
            self.set_voice(user_id, voice_name)
            await adapter.edit_message(
                recipient_id, message_ref,
                f"🎤 <b>Voice Model Updated</b>\n\n"
                f"Selected: <code>{voice_name}</code>\n"
                f"<i>Auto-routing: Enabled (English vs Taglish)</i>",
                parse_mode="HTML"
            )
            return True

        if callback_data.startswith("launch_chrome:"):
            _, target, profile = callback_data.split(":")

            # ── Master Profile Gate ──
            if profile in MASTER_PROFILES:
                session = self._master_sessions.get(user_id, {})
                session_valid = (
                    session.get("profile") == profile
                    and session.get("expires", 0) > time.time()
                )

                if session_valid:
                    await self.launch_chrome_profile(adapter, recipient_id, user_id, target, profile)
                    return True

                # Store pending — password required
                self._pending_password[user_id] = {
                    "profile": profile, "target": target, "ts": time.time()
                }
                p_label = CHROME_PROFILES.get(profile, {}).get("label", profile)
                await adapter.edit_message(
                    recipient_id, message_ref,
                    f"🔐 <b>Master Profile Detected</b>\n\n"
                    f"Profile: <code>{profile} — {p_label}</code>\n\n"
                    "This profile requires authorization.\n"
                    "Reply with the <b>access password</b> to continue:",
                    parse_mode="HTML"
                )
                return True

            # Standard profile — launch directly
            await self.launch_chrome_profile(adapter, recipient_id, user_id, target, profile)
            # Remove buttons from the profile picker after launch
            p_label = CHROME_PROFILES.get(profile, {}).get("label", profile)
            t_label = TARGETS.get(target, {}).get("label", target.upper())
            await adapter.edit_message(
                recipient_id, message_ref, 
                f"🚀 <b>Launched:</b> <code>{t_label}</code>\n"
                f"👤 <b>Profile:</b> <code>{p_label}</code>", 
                parse_mode="HTML"
            )
            return True

        # ── Fallback: Feed unhandled callbacks back into the AI Pipeline ──
        # This allows "suggestions" and dynamic buttons to work automatically
        log_event("ROUTER", f"Feedback callback received: {callback_data}")
        
        # Determine if we should treat it as a command or just a prompt
        message = callback_data
        if callback_data == "export_sheets":
            message = "Export the previously listed file structure to Google Sheets."
        
        # VISUAL FEEDBACK: Send the prompt back to the user so it appears in the chat history
        # This helps the user see what was sent and maintains the conversation flow.
        try:
            icon = "🔍" if "suggestions" in str(message_ref) or len(message) > 10 else "➡"
            await adapter.send_text(recipient_id, f"{icon} <b>Prompt:</b> {message}", parse_mode="HTML")
        except:
            # Fallback for adapters that might not support HTML or have issues
            await adapter.send_text(recipient_id, f"Prompt: {message}")
        
        # Trigger the pipeline (this mimics a user message)
        # We create a HUD so the user can see the progress of the button-triggered request.
        on_partial = None
        target = self.get_target(user_id)
        
        # If the Telegram bot is available, create a HUD for the user
        if hasattr(self.core, 'telegram_bot') and self.core.telegram_bot:
            try:
                # If we're on Telegram, use the recipient_id as the chat_id for the HUD
                hud_chat_id = recipient_id if adapter.platform_name == "telegram" else None
                
                # If not on Telegram, find the first allowed owner to notify (standard behavior)
                if not hud_chat_id:
                    from config import ALLOWED_TELEGRAM_USERS
                    if ALLOWED_TELEGRAM_USERS:
                        hud_chat_id = str(ALLOWED_TELEGRAM_USERS[0])
                
                if hud_chat_id:
                    on_partial = await self.core.telegram_bot.create_standalone_hud(
                        chat_id=hud_chat_id,
                        source=adapter.platform_name.capitalize(),
                        target=target
                    )
            except Exception as e:
                log_error("ROUTER_HUD_CREATE", e)

        async def _run_pipeline():
            try:
                res = await self.core.process_request(
                    user_id=user_id,
                    message=message,
                    target=target,
                    source=adapter.platform_name.capitalize(),
                    generate_voice=self.get_voice_mode(user_id),
                    voice_name=self.get_voice(user_id),
                    on_partial=on_partial
                )
                # DELIVER: Ensure the final result is sent to the user
                await adapter.deliver_response(recipient_id, res)
                
                # DISMISS HUD: Signal completion to delete the status box
                if on_partial:
                    await on_partial("__DONE__")
            except Exception as e:
                log_error("ROUTER_PIPELINE_TASK", e)
                if on_partial:
                    await on_partial("__DONE__") # Still dismiss on error, or update status?
                await adapter.send_text(recipient_id, f"❌ <b>Pipeline Error:</b> {str(e)}", parse_mode="HTML")

        # Trigger the pipeline in the background
        asyncio.create_task(_run_pipeline())
        return True

    def check_pending_password(self, user_id: str, password_text: str) -> Optional[Dict[str, Any]]:
        """
        Check if user has a pending password verification.
        Returns {"profile", "target", "action": "granted"|"denied"|"expired"} or None.
        """
        if user_id not in self._pending_password:
            return None

        pending = self._pending_password[user_id]

        # Expire after 90 seconds
        if time.time() - pending["ts"] > 90:
            del self._pending_password[user_id]
            return {"action": "expired"}

        profile = pending["profile"]
        target = pending["target"]
        del self._pending_password[user_id]

        if password_text.strip() == PROFILE_PASSWORD:
            # Grant 8-hour session
            SESSION_TTL = 8 * 3600
            self._master_sessions[user_id] = {
                "profile": profile, "target": target,
                "expires": time.time() + SESSION_TTL,
            }
            self.set_profile(user_id, profile)
            self.set_target(user_id, target)
            return {"action": "granted", "profile": profile, "target": target}
        else:
            return {"action": "denied"}

    # ══════════════════════════════════════════════════════════════════════
    # Command Dispatcher
    # ══════════════════════════════════════════════════════════════════════

    async def dispatch_command(self, cmd: str, adapter, recipient_id: str, user_name: str = "User"):
        """
        Route a slash command to its handler.
        Returns True if handled, False if unknown.
        """
        parts = cmd.strip().split(" ", 1)
        c = parts[0].lower()

        handlers = {
            "/start": lambda: self.cmd_start(adapter, recipient_id, user_name),
            "/help": lambda: self.cmd_help(adapter, recipient_id),
            "/status": lambda: self.cmd_status(adapter, recipient_id),
            "/target": lambda: self.cmd_target(adapter, recipient_id),
            "/new": lambda: self.cmd_new(adapter, recipient_id),
            "/newconv": lambda: self.cmd_new(adapter, recipient_id),
            "/voice": lambda: self.cmd_voice(adapter, recipient_id),
            "/terminate": lambda: self.cmd_terminate(adapter, recipient_id),
            "/restart": lambda: self.cmd_restart(adapter, recipient_id),
            "/closechrome": lambda: self.cmd_closechrome(adapter, recipient_id),
            "/activechrome": lambda: self.cmd_activechrome(adapter, recipient_id),
            "/gemini": lambda: self.cmd_gemini(adapter, recipient_id),
            "/chatgpt": lambda: self.cmd_chatgpt(adapter, recipient_id),
            "/notebooklm": lambda: self.cmd_notebooklm(adapter, recipient_id),
        }

        handler = handlers.get(c)
        if handler:
            await handler()
            return True

        return False
