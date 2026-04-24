"""
Pipeline Daemon
================
Background daemon loop for autonomous task queue processing.
Monitors a task queue and executes pipeline runs asynchronously.
"""

import asyncio
from collections import deque
from typing import Optional, Any
from core.logger import log_event


class PipelineDaemon:
    """
    Autonomous background daemon that processes queued pipeline tasks.
    Uses a 50ms polling backbone for near-instant responsiveness.
    """

    POLL_INTERVAL_MS = 50

    def __init__(self):
        self._queue: deque = deque()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {"processed": 0, "errors": 0}

    async def start(self):
        """Start the daemon polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        log_event("DAEMON", "Pipeline daemon started (50ms polling)")

    async def stop(self):
        """Stop the daemon gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log_event("DAEMON", f"Pipeline daemon stopped. Processed={self._stats['processed']}, Errors={self._stats['errors']}")

    def enqueue(self, coro, callback=None):
        """Add a coroutine to the task queue with optional callback."""
        self._queue.append((coro, callback))
        log_event("DAEMON", f"Task enqueued. Queue depth: {len(self._queue)}")

    async def _poll_loop(self):
        """Core polling loop — checks queue every 50ms."""
        while self._running:
            if self._queue:
                coro, callback = self._queue.popleft()
                try:
                    result = await coro
                    self._stats["processed"] += 1
                    if callback:
                        await callback(result)
                except Exception as e:
                    self._stats["errors"] += 1
                    log_event("DAEMON", f"Task error: {e}")
            else:
                await asyncio.sleep(self.POLL_INTERVAL_MS / 1000)

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def stats(self) -> dict:
        return dict(self._stats)
