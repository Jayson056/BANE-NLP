"""
BANE Pipeline Module — Consolidated 4-Layer Architecture
=========================================================
Merged from the original 8-layer design. Eliminates <1ms boundary overhead.

Flow:
    L1   : Intake         — Intent classification + safety guardrails (merged interpreter + guardrails)
    L1.5 : TGPT Orch.     — Intent → Structured Workflow Plan (via tgpt CLI, optional)
    L2   : Plan+Compose   — Target resolution, DB session, prompt assembly (merged planner + composer)
    L3   : BridgeExecutor — Browser dispatch + response capture + TTS (merged dispatcher + executor)
           Analyze        — Tool call extraction & iterative batch execution (inline in engine)
    RET  : Render         — Response cleanup (post-processing, not a named layer)

Each stage reads/writes to a shared PipelineContext object.
Owner: Jayson Combate / BANE NLP Agentic Core
"""

from pipeline.context import PipelineContext
from pipeline.engine import PipelineEngine
from pipeline import tgpt_orchestrator
from pipeline import intake, bridge_executor

__all__ = ["PipelineContext", "PipelineEngine", "tgpt_orchestrator", "intake", "bridge_executor"]
