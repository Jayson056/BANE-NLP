import os
import base64
import re
import mimetypes
from typing import Optional, List, Union, Callable, Dict, Any
from core.logger import log_event, log_error
from core.security import sanitize_input
from pipeline.payload_builder import build_payload
from core.database import ensure_user, get_or_create_conversation, save_message, create_ai_session, complete_ai_session
from pipeline.context_builder import build_context
from config import ALLOWED_MESSENGER_USERS, ALLOWED_TELEGRAM_USERS, TARGETS, RESPONSE_TIMEOUT

def is_authorized(user_id: Union[str, int]) -> bool:
    """Check if the user is in the allowed lists."""
    # PUBLIC ACCESS ENABLED: All users are allowed
    return True

class BaneCore:
    """
    Surgical orchestration core for the BNP pipeline.
    Handles the middle-tier logic between platform bots and the browser bridge.
    """

    def __init__(self, bridge, response_handler):
        self.bridge = bridge
        self.response_handler = response_handler
        from services.voice_engine import VoiceEngine
        self.voice_engine = VoiceEngine()
        self._partial_callbacks = {}
        self.telegram_bot = None  # Will be registered by TelegramBot
        
        # FIFO Queue Strategy: Lock ensures only one request goes to the browser at a time
        import asyncio
        self._browser_lock = asyncio.Lock()
        self.cancel_tokens = {}
        
        log_event("CORE", "BaneCore initialized with Unified Response Pipeline & Queueing Strategy.")

    async def start(self):
        """Starts the browser bridge server."""
        await self.bridge.start()

    async def stop(self):
        """Stops the browser bridge server."""
        await self.bridge.stop()

    async def new_conversation(self):
        """Clears the current conversation context in the browser."""
        payload = {
            "pipeline": "BNP",
            "type": "signal",
            "payload": {"action": "new_conversation"}
        }
        await self.bridge.broadcast(payload)
        log_event("CORE", "Signal sent: New Conversation")

    async def switch_target(self, user_id: Union[str, int], target: str):
        """Explicitly switch the current AI target in the browser."""
        payload = {
            "pipeline": "BNP",
            "type": "signal",
            "payload": {"action": "switch_target", "target": target}
        }
        await self.bridge.broadcast(payload)
        log_event("CORE", f"Signal sent: Switch Target to {target} (User: {user_id})")

    async def navigate_to(self, url: str):
        """Commands the browser to navigate to a specific URL."""
        payload = {
            "pipeline": "BNP",
            "type": "signal",
            "payload": {"action": "navigate", "url": url}
        }
        await self.bridge.broadcast(payload)
        log_event("CORE", f"Signal sent: Navigate to {url}")

    async def process_request(
        self,
        user_id: Union[str, int],
        message: str = "",
        target: Optional[str] = None,
        source: str = "Messenger",
        file_path: Optional[str] = None,
        forced_filename: Optional[str] = None,
        file_data: Optional[dict] = None,
        file_paths: Optional[List[str]] = None,
        file_datas: Optional[List[dict]] = None,
        on_partial: Optional[Callable] = None,
        generate_voice: bool = True,
        chrome_profile: str = "",
        voice_name: Optional[str] = None
    ) -> Union[str, dict]:
        """
        The primary entry point for all BANE NLP requests.
        Delegates completely to the PipelineEngine.
        """
        from pipeline.engine import PipelineEngine
        
        # Instantiate the engine pipeline (it handles its own locking internally)
        engine = PipelineEngine(self.bridge, self.response_handler, self.voice_engine)
        
        # We share our existing lock with the engine to ensure cross-module sync
        engine._browser_lock = self._browser_lock
        engine.cancel_tokens = self.cancel_tokens
        self.cancel_tokens[user_id] = False # Reset token for this session
        
        return await engine.run(
            user_id=user_id,
            message=message,
            target=target,
            source=source,
            file_path=file_path,
            file_paths=file_paths,
            file_data=file_data,
            file_datas=file_datas,
            forced_filename=forced_filename,
            on_partial=on_partial,
            generate_voice=generate_voice,
            chrome_profile=chrome_profile,
            voice_name=voice_name
        )
