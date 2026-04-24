"""
Pipeline Context
=================
Shared state object that flows through every pipeline stage.
Each stage reads what it needs and writes its output here.
"""

import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable


@dataclass
class PipelineContext:
    """
    The unified state bag passed through all pipeline stages.
    
    Created once per user request, passed through:
        Interpreter → Analyzer → Planner → Context → Composer →
        Guardrails → Dispatcher → Engine → Executor
    """
    # ── Request Identity ──
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    # ── User Info ──
    user_id: str = ""
    platform: str = ""           # "telegram" | "messenger"
    db_user_id: str = ""
    conversation_id: str = ""
    chrome_profile: str = ""     # Active Chrome profile dir (e.g. "Profile 7")

    # ── Raw Input ──
    raw_message: str = ""
    clean_message: str = ""
    file_paths: List[str] = field(default_factory=list)
    file_datas: List[Dict[str, Any]] = field(default_factory=list)
    forced_filename: Optional[str] = None

    # ── Interpreter Output ──
    intent: str = "general"      # "general" | "image" | "video" | "code" | "document" | "voice"
    inline_target: Optional[str] = None  # @gemini, @chatgpt, @notebooklm prefix

    # ── TGPT Orchestrator Output (Layer 1.5) ──
    tgpt_workflow_plan: Optional[str] = None  # TGPT-generated structured workflow plan
    
    # ── Analyzer Output ──
    has_user_files: bool = False
    is_image_request: bool = False
    is_video_request: bool = False
    detected_language: str = "en"

    # ── Planner Output ──
    target: str = "chatgpt"      # Final resolved AI target
    session_id: str = ""
    skip_persona_injection: bool = False  # True for NotebookLM (pinned sources)
    skip_db_injection: bool = False

    # ── Context Stage Output ──
    dynamic_context: str = ""    # Conversation history block
    memory_context: str = ""     # Knowledge memory block

    # ── V2: Context Compaction ──
    token_estimate: int = 0           # Approximate token usage for context
    compacted_history: str = ""       # Compacted version of conversation history
    context_was_compacted: bool = False  # Whether compaction was triggered

    # ── Composer Output ──
    final_prompt: str = ""       # The fully assembled prompt
    payload_files: List[Dict[str, Any]] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    generate_voice: bool = True

    # ── Guardrails Output ──
    passed_guardrails: bool = True
    guardrail_reason: str = ""

    # ── Engine/Executor Output ──
    raw_response: Optional[Dict[str, Any]] = None
    response_text: str = ""
    suggestions: List[str] = field(default_factory=list)
    audio_path: Optional[str] = None
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # ── Callbacks ──
    on_partial: Optional[Callable] = None

    # ── Error Tracking ──
    error: Optional[str] = None
    stages_completed: List[str] = field(default_factory=list)

    def mark_stage(self, stage_name: str):
        """Record that a pipeline stage completed successfully."""
        self.stages_completed.append(stage_name)

    @property
    def is_master_profile(self) -> bool:
        """Returns True if the active Chrome profile is a Master (gated) profile."""
        from config import MASTER_PROFILES
        return self.chrome_profile in MASTER_PROFILES

    @property
    def elapsed_ms(self) -> float:
        """Time elapsed since request started, in milliseconds."""
        return (time.time() - self.timestamp) * 1000

    @property
    def is_failed(self) -> bool:
        return self.error is not None
