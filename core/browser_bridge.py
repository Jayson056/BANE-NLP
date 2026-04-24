"""
BNP Browser Communication Bridge
==================================
WebSocket server that acts as the bridge between Bane Core (Python)
and the Chrome extension. Supports bidirectional messaging.
"""

import asyncio
import json
from typing import Callable, Awaitable, Optional, Set, Dict, Any, Union

import websockets
# Import the base connection type for type hinting
try:
    from websockets.server import WebSocketServerProtocol as ServerConnection
except ImportError:
    # Fallback for different versions
    from websockets.legacy.server import WebSocketServerProtocol as ServerConnection

from config import WEBSOCKET_HOST, WEBSOCKET_PORT
from core.logger import system_logger, log_event, log_error
from core.security import validate_payload


class BrowserBridge:
    """
    WebSocket server that communicates with the Chrome extension.
    Routes messages to the specific (target, chrome_profile) pair.
    """

    def __init__(self):
        self._server: Any = None
        self._clients: Set[ServerConnection] = set()
        # Maps client websocket → {"target": str, "chrome_profile": str}
        self._client_meta: Dict[ServerConnection, Dict[str, str]] = {}
        # Maps msg_id → (asyncio.Future, ServerConnection)
        self._response_futures: Dict[str, tuple[asyncio.Future, ServerConnection]] = {}
        self._partial_callbacks: Dict[str, Callable] = {}
        self._on_response: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
        # Pre-registered profile: set by TelegramBot right before launching Chrome.
        # When the extension connects and reports "Default", this value is used instead.
        self._pending_profile: Optional[str] = None

    def set_pending_profile(self, profile: str) -> None:
        """
        Pre-register the profile that is about to connect.
        Call this immediately before launching Chrome with a specific profile.
        The next connecting extension that reports 'Default' or empty will be
        assigned this profile name automatically.
        """
        self._pending_profile = profile
        log_event("BRIDGE", f"Pending profile registered: '{profile}'")


    def set_response_handler(self, handler: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Set the callback for when a response is received from the browser."""
        self._on_response = handler

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self._handle_connection,
            WEBSOCKET_HOST,
            WEBSOCKET_PORT,
            ping_interval=10,      # V2: Proactive dead-connection detection every 10s
            ping_timeout=20,       # V2: Kill unresponsive sockets after 20s silence
            max_size=20 * 1024 * 1024  # 20MB — needed for base64 image payloads from Gemini
        )
        log_event("BRIDGE", f"WebSocket server started on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
        # V2: Start background stale-client cleanup cycle
        asyncio.ensure_future(self._cleanup_stale_clients_loop())

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            log_event("BRIDGE", "WebSocket server stopped")

    async def _cleanup_stale_clients_loop(self) -> None:
        """V2: Periodically evict dead/stale WebSocket connections every 5 seconds."""
        while True:
            await asyncio.sleep(5)
            stale = []
            for ws in list(self._clients):
                if ws.state.name == "CLOSED":
                    stale.append(ws)
            for ws in stale:
                self._clients.discard(ws)
                self._client_meta.pop(ws, None)
                # Cancel any pending futures bound to this socket
                stale_futures = [mid for mid, (fut, sock) in self._response_futures.items() if sock is ws]
                for mid in stale_futures:
                    fut, _ = self._response_futures.pop(mid)
                    if not fut.done():
                        fut.set_result(None)
            if stale:
                log_event("BRIDGE", f"[V2 Cleanup] Evicted {len(stale)} stale connection(s). Active: {len(self._clients)}")

    async def _handle_connection(self, websocket: ServerConnection, path: str = "") -> None:
        """Handle a new WebSocket connection from the Chrome extension."""
        self._clients.add(websocket)
        remote = websocket.remote_address
        log_event("BRIDGE", f"Chrome extension connected: {remote}")

        try:
            async for raw_message in websocket:
                if isinstance(raw_message, (str, bytes)):
                    await self._handle_message(str(raw_message), websocket)
        except websockets.exceptions.ConnectionClosed as e:
            log_event("BRIDGE", f"Connection closed: {remote} ({e})")
        except Exception as e:
            log_error("BRIDGE", e)
        finally:
            self._clients.discard(websocket)
            self._client_meta.pop(websocket, None)
            log_event("BRIDGE", f"Chrome extension disconnected: {remote}")

            # Resolve pending futures that were waiting for THIS specific connection
            for msg_id in list(self._response_futures.keys()):
                future, conn = self._response_futures.get(msg_id, (None, None))
                if conn is websocket and future and not future.done():
                    self._response_futures.pop(msg_id, None)
                    future.set_exception(ConnectionError("Chrome extension disconnected during request."))

    async def _handle_message(self, raw: str, websocket: ServerConnection) -> None:
        """Process an incoming message from the Chrome extension."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log_error("BRIDGE_PARSE", e)
            return

        valid, err = validate_payload(data)
        if not valid:
            system_logger.warning(f"Invalid payload from browser: {err}")
            return

        msg_type = data.get("type")
        msg_id = data.get("id")

        if msg_type == "ping":
            # Keep-alive ping from the background service worker — reply with pong
            try:
                pong = json.dumps({"pipeline": "BNP", "type": "pong", "id": data.get("id", ""), "payload": {}})
                await websocket.send(pong)
            except Exception:
                pass
            return

        if msg_type == "response" or msg_type == "partial_response":
            is_partial = data.get("status") == "partial"
            
            if not is_partial:
                log_event("BRIDGE", f"Final response received for request {msg_id}")
                if msg_id and msg_id in self._response_futures:
                    future, _ = self._response_futures.pop(msg_id)
                    if not future.done():
                        future.set_result(data)
            else:
                log_event("BRIDGE", f"Partial update received for request {msg_id}")
                if msg_id and msg_id in self._partial_callbacks:
                    text_payload = data.get("payload", {}).get("text", "")
                    try:
                        await self._partial_callbacks[msg_id](text_payload)
                    except Exception as e:
                        log_error("BRIDGE_PARTIAL_CALLBACK", e)

            if self._on_response:
                await self._on_response(data)

        elif msg_type == "status":
            status_val = data.get("payload", {}).get("status", "")

            # ── Background service worker tab_connected event ──────────────
            # The BG worker reports individual AI tabs as they are discovered.
            # Register those tabs so we can route prompts to them.
            if status_val == "tab_connected":
                tab_target = data.get("payload", {}).get("target", "").lower()
                tab_profile = data.get("payload", {}).get("chrome_profile", "").strip()
                tab_id = data.get("payload", {}).get("tab_id")
                log_event("BRIDGE", f"Tab registered via BG worker: target={tab_target} profile={tab_profile} tab={tab_id}")
                # Register the background socket as a relay for this target+profile
                if tab_target and tab_target not in ("background", "unknown"):
                    # Store or update the meta for this background WS connection
                    existing_meta = self._client_meta.get(websocket, {})
                    # Only update if this target isn't already registered to another socket
                    target_already_registered = any(
                        meta.get("target") == tab_target and meta.get("chrome_profile") == tab_profile
                        for c, meta in self._client_meta.items() if c is not websocket
                    )
                    if not target_already_registered:
                        self._client_meta[websocket] = {
                            "target": tab_target,
                            "chrome_profile": tab_profile,
                            "relay": "background_worker",
                        }
                        log_event("BRIDGE", f"Background relay registered: target={tab_target} profile={tab_profile}")
                return

            # ── background service worker connected status ─────────────────
            # The BG worker sends target="background" on first connect.
            # Register it but don't route normal AI prompts to it directly.
            if data.get("payload", {}).get("target", "") == "background":
                self._client_meta[websocket] = {
                    "target": "background",
                    "chrome_profile": data.get("payload", {}).get("chrome_profile", ""),
                    "relay": "background_worker",
                }
                log_event("BRIDGE", f"Background service worker registered (profile={data.get('payload', {}).get('chrome_profile', '')})")
                return

            # fall through to normal status handling — set flag for block below
            _orig_status = True

        if msg_type == "status" and locals().get("_orig_status"):
            target  = data.get("payload", {}).get("target", "unknown").lower()
            profile = data.get("payload", {}).get("chrome_profile", "").strip()
            status  = data.get("payload", {}).get("status", "unknown")

            # ── Pending profile claim ──────────────────────────────────────────
            # If the extension reports "Default" or empty (because chrome.storage
            # hasn't been seeded yet), and TelegramBot pre-registered a pending
            # profile right before launching Chrome, claim it for this connection.
            if self._pending_profile and (not profile or profile.lower() == "default"):
                log_event(
                    "BRIDGE",
                    f"Claiming pending profile '{self._pending_profile}' "
                    f"for connection that reported '{profile or 'empty'}'"
                )
                profile = self._pending_profile
                self._pending_profile = None  # consume — one-shot

            # ── Deduplication: evict stale connections for same target+profile ─
            # When a tab reloads or the extension reconnects, the old WebSocket
            # lingers in _clients alongside the new one. This causes both to
            # receive the same payload → double injection in ChatGPT/Gemini.
            # Evict any OTHER socket already registered for this (target, profile).
            if profile and target:
                stale = [
                    c for c, meta in self._client_meta.items()
                    if c is not websocket
                    and meta.get("target") == target
                    and meta.get("chrome_profile") == profile
                ]
                for c in stale:
                    log_event(
                        "BRIDGE",
                        f"Evicting stale connection for profile='{profile}' "
                        f"target='{target}' — replaced by new socket."
                    )
                    self._clients.discard(c)
                    self._client_meta.pop(c, None)
                    # Force close to trigger the finally block and cleanup futures
                    asyncio.create_task(c.close())

            self._client_meta[websocket] = {"target": target, "chrome_profile": profile}
            log_event("BRIDGE", f"Status update: {status} | Target: {target} | Profile: {profile or '(any)'}")

        elif msg_type == "log":
            payload = data.get("payload", {})
            src = payload.get("source", "Browser")
            text = payload.get("text", "")
            log_event("BRIDGE_LOG", f"[{src}] {text}")

    async def send_payload(self, payload: Dict[str, Any], timeout: float = 120.0, on_partial: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """
        Send a payload to the SPECIFIC (target, chrome_profile) Chrome extension
        and wait for a response.

        Routing logic:
          1. Filter clients by target (required).
          2. If payload has a non-empty chrome_profile, further filter by profile.
          3. If chrome_profile is empty, fall back to target-only (legacy broadcast).
          4. Among matched clients, dispatch only to the MOST RECENT one (LIFO)
             to avoid tab-clashing.
          5. If no matching client found → return None (caller handles the error).
        """
        if not self._clients:
            system_logger.error("No Chrome extension connected!")
            return None

        target  = payload.get("target", "").lower()
        
        # ── Target Normalization ───────────────────────────────────────────
        # Normalize sub-targets (like gemini_general/gemini_custom) back to 
        # the base target name (gemini) so the dispatcher can find the 
        # connected Chrome extension tab.
        if target.startswith("gemini_"):
            target = "gemini"
            payload["target"] = target
            
        profile = payload.get("chrome_profile", "").strip()
        msg_id  = str(payload.get("id", ""))
        json_str = json.dumps(payload)

        # ── Step 1: match by target ──
        target_clients = [
            c for c, meta in self._client_meta.items()
            if meta.get("target") == target
        ]

        if not target_clients:
            system_logger.warning(
                f"No extension connected for target '{target}'. "
                "Injection aborted to prevent cross-profile leakage."
            )
            return None

        # ── Step 2: narrow by profile if specified ──
        if profile:
            profile_clients = [
                c for c in target_clients
                if self._client_meta[c].get("chrome_profile") == profile
            ]
            if profile_clients:
                dispatch_list = [profile_clients[-1]]   # most-recent match
                log_event("BRIDGE", f"Profile-matched dispatch: profile='{profile}', target='{target}'")
            else:
                # Profile specified but NOT connected — signal caller
                system_logger.warning(
                    f"Profile '{profile}' is NOT connected for target '{target}'. "
                    "Returning None so dispatcher can notify the user."
                )
                return None
        else:
            # Legacy / no profile specified — send to most-recent target client
            dispatch_list = [target_clients[-1]]
            log_event("BRIDGE", f"Target-only dispatch (no profile): target='{target}'")

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        # We'll set the websocket association in the loop below once we know which client we chose
        
        if on_partial and msg_id:
            self._partial_callbacks[msg_id] = on_partial

        disconnected: Set[ServerConnection] = set()
        for client in dispatch_list:
            try:
                # Register future with this specific client
                if msg_id:
                    self._response_futures[msg_id] = (future, client)
                
                await client.send(json_str)
                meta = self._client_meta.get(client, {})
                log_event("BRIDGE", f"Payload dispatched → {client.remote_address} "
                                    f"[Target: {target} | Profile: {meta.get('chrome_profile') or 'any'}]")
            except Exception as e:
                log_error("BRIDGE_SEND", e)
                disconnected.add(client)
                if msg_id and msg_id in self._response_futures:
                    self._response_futures.pop(msg_id, None)

        for dc in disconnected:
            self._clients.discard(dc)
            self._client_meta.pop(dc, None)

        if msg_id:
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                self._response_futures.pop(msg_id, None)
                system_logger.warning(f"Timeout waiting for response to {msg_id}")
                return None
            finally:
                self._partial_callbacks.pop(msg_id, None)
        return None

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """Send a payload to all connected clients without waiting for a response."""
        if not self._clients:
            return
            
        json_str = json.dumps(payload)
        disconnected: Set[ServerConnection] = set()
        for client in self._clients:
            try:
                await client.send(json_str)
            except Exception:
                disconnected.add(client)
        self._clients -= disconnected

    @property
    def is_connected(self) -> bool:
        """Whether at least one Chrome extension client is connected."""
        return len(self._clients) > 0

    @property
    def client_count(self) -> int:
        """Number of connected Chrome extension clients."""
        return len(self._clients)

    def is_profile_connected(self, chrome_profile: str, target: str = "") -> bool:
        """
        Check if a specific Chrome profile (and optionally a specific target)
        has an active WebSocket connection.

        Args:
            chrome_profile: Profile directory name, e.g. "Profile 7".
            target:         Optional LLM target filter ("gemini", "chatgpt", etc.).
                            If empty, checks across all targets.
        """
        target = target.lower()
        if target.startswith("gemini_"):
            target = "gemini"

        for meta in self._client_meta.values():
            if meta.get("chrome_profile") == chrome_profile:
                if not target or meta.get("target") == target:
                    return True
        return False

    def get_active_profiles(self) -> Dict[str, str]:
        """
        Return a dict of all currently connected profiles and their targets.
        Format: {"Profile 7": "gemini", "Profile 4": "chatgpt", ...}
        """
        result = {}
        for meta in self._client_meta.values():
            p = meta.get("chrome_profile", "")
            t = meta.get("target", "")
            if p:
                result[p] = t
        return result

    def get_active_connections(self) -> Set[str]:
        """Return a set of target names currently connected (e.g. {'gemini', 'chatgpt'})."""
        return {meta.get("target", "") for meta in self._client_meta.values() if meta.get("target")}
