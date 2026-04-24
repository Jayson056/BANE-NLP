"""
Ephemeral Worker (V2 Phase 3: Agency)
=======================================
Implements the Manager-Worker pattern for multi-agent orchestration.

Architecture:
    Manager (tgpt_orchestrator.py) creates WorkerTasks
        ↓
    EphemeralWorker spawns into an isolated Chrome profile
        ↓
    Worker executes a narrow, scoped goal via PipelineEngine.run()
        ↓
    Clean WorkerResult returned to Manager (no raw DOM/HTML)
        ↓
    Worker context is discarded — no state leakage

Design Decisions:
    - Workers are fully isolated: each gets its own Chrome profile
    - Workers have a configurable timeout (default 60s) to prevent runaway tasks
    - Results are sanitized: only clean text is returned to the Manager
    - The Manager never gets browsing tools — it delegates instead
"""

import asyncio
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

from core.logger import log_event, log_error


class WorkerStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class WorkerTask:
    """
    A unit of work delegated by the Manager to an Ephemeral Worker.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    goal: str = ""                    # The scoped instruction for this worker
    target_profile: str = ""          # Chrome profile to execute in (e.g., "Profile 2")
    target_llm: str = "gemini"        # Which LLM target to use
    parent_request_id: str = ""       # The originating user request ID
    user_id: str = ""                 # The originating user ID
    platform: str = "telegram"        # Source platform
    status: WorkerStatus = WorkerStatus.PENDING
    result: str = ""                  # Clean text result from the worker
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class WorkerResult:
    """
    Clean output from a worker, stripped of any DOM/HTML artifacts.
    """
    task_id: str
    success: bool
    text: str                         # The clean text output
    elapsed_ms: float
    error: Optional[str] = None


class EphemeralWorker:
    """
    Spawns a scoped pipeline execution in an isolated Chrome profile.
    The worker runs a single goal and returns clean data to the Manager.
    """

    def __init__(self, engine, timeout: float = 60.0):
        """
        Args:
            engine:  Reference to the PipelineEngine instance.
            timeout: Maximum seconds before the worker is killed.
        """
        self.engine = engine
        self.timeout = timeout

    async def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Execute a WorkerTask through the pipeline and return a clean result.

        The worker:
            1. Marks itself as RUNNING
            2. Calls engine.run() with the worker's isolated chrome_profile
            3. Sanitizes the output (strips HTML, truncates)
            4. Returns a WorkerResult

        On timeout or error, returns a failed WorkerResult.
        """
        task.status = WorkerStatus.RUNNING
        start_time = time.time()

        log_event("WORKER", (
            f"[{task.task_id}] Starting worker → "
            f"Profile: {task.target_profile}, LLM: {task.target_llm}, "
            f"Goal: {task.goal[:80]}..."
        ))

        try:
            result = await asyncio.wait_for(
                self.engine.run(
                    user_id=task.user_id,
                    message=task.goal,
                    target=task.target_llm,
                    source=task.platform,
                    chrome_profile=task.target_profile,
                    generate_voice=False,  # Workers never generate voice
                    on_partial=None,       # No HUD updates for background workers
                ),
                timeout=self.timeout,
            )

            elapsed = (time.time() - start_time) * 1000
            task.completed_at = time.time()

            # Sanitize result
            if isinstance(result, dict):
                clean_text = result.get("response_text", str(result))
            else:
                clean_text = str(result) if result else ""

            clean_text = self._sanitize(clean_text)

            if clean_text:
                task.status = WorkerStatus.COMPLETED
                task.result = clean_text
                log_event("WORKER", f"[{task.task_id}] Completed in {elapsed:.0f}ms ({len(clean_text)} chars)")
                return WorkerResult(
                    task_id=task.task_id,
                    success=True,
                    text=clean_text,
                    elapsed_ms=elapsed,
                )
            else:
                task.status = WorkerStatus.FAILED
                task.error = "Worker returned empty result"
                log_event("WORKER", f"[{task.task_id}] Failed: empty result")
                return WorkerResult(
                    task_id=task.task_id,
                    success=False,
                    text="",
                    elapsed_ms=elapsed,
                    error="Worker returned empty result",
                )

        except asyncio.TimeoutError:
            elapsed = (time.time() - start_time) * 1000
            task.status = WorkerStatus.TIMEOUT
            task.error = f"Worker timed out after {self.timeout}s"
            task.completed_at = time.time()
            log_error("WORKER", Exception(f"[{task.task_id}] Timeout after {self.timeout}s"))
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                text="",
                elapsed_ms=elapsed,
                error=f"Worker timed out after {self.timeout}s",
            )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            task.status = WorkerStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            log_error("WORKER", e)
            return WorkerResult(
                task_id=task.task_id,
                success=False,
                text="",
                elapsed_ms=elapsed,
                error=str(e),
            )

    @staticmethod
    def _sanitize(text: str) -> str:
        """
        Strip raw HTML tags and excessive whitespace from worker output.
        Workers return CLEAN TEXT only — no DOM artifacts.
        """
        import re
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Truncate extremely long outputs (workers should be concise)
        max_len = 4000
        if len(text) > max_len:
            text = text[:max_len] + "\n\n[... Worker output truncated]"
        return text.strip()
