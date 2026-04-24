"""
Channel Adapter — Unified Communication Interface
===================================================
Abstract base class for all communication platform adapters.
Each platform (Telegram, Messenger, Web, etc.) implements this interface
so the CommandRouter can send responses without knowing the platform.

Design:
  - Adapters are THIN: they only wrap platform-specific delivery APIs.
  - Business logic lives in CommandRouter, not here.
  - Buttons are represented as simple dicts: {"label": str, "data": str}
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union


class ChannelAdapter(ABC):
    """Abstract communication channel for sending messages to users."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g. 'telegram', 'messenger')."""
        ...

    @abstractmethod
    async def send_text(self, recipient_id: str, text: str, **kwargs) -> Optional[str]:
        """
        Send a text message. Returns message ID if available.
        
        kwargs may include:
          - parse_mode: 'HTML' or 'Markdown' (Telegram)
          - reply_to: message ID to reply to
        """
        ...

    @abstractmethod
    async def send_buttons(self, recipient_id: str, text: str, buttons: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """
        Send a message with interactive buttons.
        
        Each button is {"label": "Display Text", "data": "callback_data_string"}.
        Platform adapters convert to their native format:
          - Telegram → InlineKeyboardButton
          - Messenger → Quick Replies
        """
        ...

    @abstractmethod
    async def edit_message(self, recipient_id: str, message_ref: Any, text: str, buttons: Optional[List[Dict[str, str]]] = None, **kwargs) -> None:
        """
        Edit an existing message. If buttons is None, remove buttons.
        For platforms that don't support editing (Messenger), send a new message.
        """
        ...

    @abstractmethod
    async def send_typing(self, recipient_id: str) -> None:
        """Show typing indicator."""
        ...

    @abstractmethod
    async def send_image(self, recipient_id: str, image_data: str) -> None:
        """Send an image (path or URL)."""
        ...

    @abstractmethod
    async def send_audio(self, recipient_id: str, file_path: str) -> None:
        """Send an audio file."""
        ...

    @abstractmethod
    async def send_video(self, recipient_id: str, video_data: str) -> None:
        """Send a video (path or URL)."""
        ...

    @abstractmethod
    async def deliver_response(self, recipient_id: str, res: Union[str, Dict[str, Any]]) -> None:
        """
        Deliver a complex AI response bundle to the user.
        The bundle may contain text, images, audio, and suggestions.
        """
        ...

    async def delete_message(self, recipient_id: str, message_ref: Any) -> None:
        """Delete a message. Default: no-op (not all platforms support this)."""
        pass
