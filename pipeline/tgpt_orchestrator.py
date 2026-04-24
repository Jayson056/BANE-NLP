"""
TGPT Orchestrator (Layer 1.5)
==============================
Intent-to-Workflow Interpreter using the TGPT CLI.

Architecture (per BANE Advanced Intent-Driven Workflow Proposal):
  Raw User Intent (from Layer 1: Interpreter)
      ↓
  TGPT CLI Analysis  ← THIS MODULE
      ↓
  Structured Workflow Plan (specialized prompt tailored for the target LLM)
      ↓
  Enriched PipelineContext → Layer 2: Guardrails

Design Decisions:
  - Lightweight: TGPT is called with --quiet for clean output only
  - Graceful degradation: If tgpt is missing/times out, pipeline continues normally
  - Skip logic: Short messages and simple intents bypass orchestration to preserve speed
  - BANE Brain reference is maintained in every orchestration prompt
  - Original user intent is always preserved and appended for full context continuity
"""

import asyncio
import os
import re
from typing import Optional

from pipeline.context import PipelineContext
from core.logger import log_event, log_error


# ── Configuration ──────────────────────────────────────────────────────────────
TGPT_TIMEOUT_SECONDS = 25        # Max wait for TGPT CLI response
TGPT_MIN_MSG_LENGTH  = 25        # Skip orchestration for very short messages
TGPT_MAX_PLAN_LENGTH = 2000      # Cap workflow plan length to keep payloads sane


# ── Internal Helpers ───────────────────────────────────────────────────────────

def _build_orchestration_prompt(ctx: PipelineContext) -> str:
    """
    Construct the meta-prompt sent to TGPT for workflow planning.
    Maintains BANE Brain identity and preserves original user intent.
    """
    target_desc = {
        "gemini":      "Google Gemini — supports JSON tool calls, code execution, file analysis",
        "chatgpt":     "OpenAI ChatGPT  — general intelligence, code generation, analysis",
        "notebooklm":  "Google NotebookLM — document synthesis, knowledge base Q&A",
    }.get(ctx.target, ctx.target.upper())

    has_files = "Yes (Files/images already uploaded to target LLM natively)" if (ctx.file_paths or ctx.file_datas) else "No"

    # ── Fetch Profile & Subject Context ──
    from config import CHROME_PROFILES, PROFILE_SUBJECTS
    p_label = CHROME_PROFILES.get(ctx.chrome_profile, {}).get("label", ctx.chrome_profile or "Default")
    profile_str = f"{ctx.chrome_profile or 'Default'} ({p_label})"
    
    subject_info = PROFILE_SUBJECTS.get(ctx.chrome_profile)
    subject_context = ""
    if subject_info:
        subject_context = (
            f"=======================================\n"
            f"ACADEMIC SUBJECT CONTEXT:\n"
            f"  Course  : {subject_info['course']}\n"
            f"  Type    : {subject_info['type']}\n"
            f"  Schedule: {subject_info['schedule']}\n"
            f"  Student : {subject_info['student']}\n"
            f"=======================================\n\n"
        )

    # Read context files requested by user for TGPT awareness
    try:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        kb_path = os.path.join(base_dir, "Docs", "InjectionHeaderContext", "BANE_NLP_BRAIN_knowledge.md")
        if os.path.exists(kb_path):
            with open(kb_path, 'r', encoding='utf-8') as f:
                kb_content = f.read()
        else:
            kb_content = "[KB NOT FOUND]"
            log_error("TGPT_ORCH_FILES", f"Knowledge base not found at: {kb_path}")

        notes_path = os.path.join(r"D:\Project_Workspace", "MyNotes", "Next_Plan_Notes.txt")
        if os.path.exists(notes_path):
            with open(notes_path, 'r', encoding='utf-8') as f:
                notes_content = f.read()
        else:
            notes_content = ""
    except Exception as e:
        log_error("TGPT_ORCH_FILES", f"Error reading context files: {e}")
        kb_content = ""
        notes_content = ""

    return (
        f"[BANE NLP WORKFLOW ORCHESTRATOR]\n\n"
        f"Your task: Analyze the raw user intent below and revise it into a clear, "
        f"structured Workflow Plan Action specifically designed for the target LLM "
        f"and active profile context.\n\n"
        f"TARGET LLM    : {target_desc}\n"
        f"CHROME PROFILE: {profile_str}\n"
        f"INTENT TYPE   : {ctx.intent}\n"
        f"HAS FILES     : {has_files}\n"
        f"USER ID       : {ctx.user_id}\n"
        f"SOURCE        : {ctx.platform.upper()}\n\n"
        f"=======================================\n"
        f"D: DRIVE MAP (FILESYSTEM AWARENESS):\n"
        f"  D:\\Project_Workspace\\   ← DEFAULT for user project operations\n"
        f"  D:\\Bane_NLP\\            ← BANE engine (READ-ONLY)\n"
        f"  D:\\Meter-Reader-Pro\\    ← Mobile app project\n"
        f"  D:\\WebDev\\              ← Web dev projects\n"
        f"  D:\\MYPROJECT\\           ← Legacy projects\n"
        f"  RULE: 'my workspace' / 'my projects' → D:\\Project_Workspace\n"
        f"  RULE: NEVER default to D:\\Bane_NLP for user file operations\n"
        f"=======================================\n\n"
        f"=======================================\n"
        f"DESIGNATED SAVE PATHS (MANDATORY — always use these):\n"
        f"  TTS / Audio output  -> {os.path.join(base_dir, 'temp_audio')}\n"
        f"  Screenshots         -> {os.path.join(base_dir, 'Screenshot')}\n"
        f"  AI-generated images -> {os.path.join(base_dir, 'generated_images')}\n"
        f"=======================================\n\n"
        f"{subject_context}"
        f"=======================================\n"
        f"PROJECT & MCP TOOL KNOWLEDGE BASE:\n"
        f"{kb_content}\n"
        f"=======================================\n"
        f"PROJECT NOTES / ACTIVE TASKS:\n"
        f"{notes_content}\n"
        f"=======================================\n\n"
        f"RAW USER INTENT:\n"
        f"───────────────────────────────────────\n"
        f"{ctx.clean_message}\n"
        f"───────────────────────────────────────\n\n"
        f"OUTPUT RULES:\n"
        f"1. If the task is COMPLEX (multi-step, file ops, code, deployment): "
        f"produce a numbered action plan + enriched prompt tailored for the target LLM & Profile.\n"
        f"2. If the task is SIMPLE (greeting, question, explanation): "
        f"output the original message verbatim — NO changes.\n"
        f"3. ALWAYS preserve the user's original intent. Add clarity, not noise.\n"
        f"4. ONLY provide workflows using the exact MCP tools documented above.\n"
        f"5. When the plan includes TTS or screenshots, ALWAYS include the exact save path from DESIGNATED SAVE PATHS.\n"
        f"6. If HAS FILES is Yes, explicitly instruct the AI to directly analyze the attached images/files natively from its context window. Do NOT instruct the AI to use MCP file tools (like list_dir or read_file) to read the user's attachments.\n"
        f"7. WORKSPACE: When user mentions 'my workspace', 'Project_Workspace', or asks to list/create files without a path, ALWAYS use D:\\Project_Workspace — NEVER D:\\Bane_NLP.\n"
        f"8. Output ONLY the final revised prompt. No preamble. No commentary."
    )


async def _invoke_tgpt(prompt: str) -> Optional[str]:
    """
    Spawn the TGPT CLI subprocess and capture its output.
    Returns the cleaned output string, or None on failure/timeout.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "tgpt", "--quiet", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        log_error("TGPT_ORCH", "TGPT CLI not found in PATH — skipping orchestration layer.")
        return None
    except Exception as e:
        log_error("TGPT_ORCH", f"Failed to spawn TGPT process: {e}")
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=TGPT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        log_error("TGPT_ORCH", f"TGPT timed out after {TGPT_TIMEOUT_SECONDS}s — skipping orchestration.")
        return None

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        log_error("TGPT_ORCH", f"TGPT exited {proc.returncode}: {err[:200]}")
        return None

    output = stdout.decode("utf-8", errors="replace").strip()
    return output[:TGPT_MAX_PLAN_LENGTH] if output else None


def _should_skip(ctx: PipelineContext) -> tuple[bool, str]:
    """
    Determine if orchestration should be bypassed.
    
    Strategy: ONLY invoke TGPT for complex multi-step tasks.
    Skip for everything else (questions, explanations, conversations).
    Returns (skip: bool, reason: str).
    """
    msg = ctx.clean_message.strip()
    lower = msg.lower()

    if len(msg) < TGPT_MIN_MSG_LENGTH:
        return True, f"message too short ({len(msg)} chars)"

    if getattr(ctx, "has_user_files", False):
        # Only skip TGPT for pure file analysis (no action verbs in message)
        # If the user attached files BUT also has complex instructions, let TGPT plan
        file_action_indicators = [
            "save ", "deploy", "create ", "build ", "convert ",
            "analyze and", "then ", "after that", "upload",
            "move ", "copy ", "rename", "extract",
        ]
        has_file_actions = any(ind in lower for ind in file_action_indicators)
        if not has_file_actions:
            return True, "user attached files/images for direct analysis (no action verbs)"

    if getattr(ctx, "is_image_request", False):
        return True, "image generation request (direct pass-through)"

    if ctx.is_video_request:
        return True, "video generation request (direct pass-through)"

    # Skip simple one-shot conversational messages
    simple_re = re.compile(
        r"^(hi|hello|hey|ok|yes|no|thanks|okay|sup|yo|ping|test|status)\b",
        re.IGNORECASE
    )
    if simple_re.match(msg):
        return True, "simple conversational message"

    # ── Intent-Based Skip: Only orchestrate COMPLEX multi-step tasks ──
    # If the message does NOT contain any complex task indicators,
    # it's a simple query that the target LLM can handle directly.
    complex_indicators = [
        "create ", "build ", "deploy", "generate ", "make ",
        "write code", "write a script", "write a program",
        "set up", "setup", "configure", "install",
        "automate", "schedule", "run ", "execute",
        "fix the", "debug ", "refactor",
        "step by step", "step-by-step", "multi-step",
        "then ", "after that", "and then",
        "save to", "save it", "download",
        "upload", "send to", "push to",
        "convert ", "migrate", "move ",
    ]

    has_complex = any(ind in lower for ind in complex_indicators)

    if not has_complex:
        return True, "no complex task indicators (simple query → direct to LLM)"

    return False, ""


# ── Public Entry Point ─────────────────────────────────────────────────────────

async def run(ctx: PipelineContext, engine=None) -> PipelineContext:
    """
    Layer 1.5: TGPT Orchestrator

    Reads the cleaned user intent from ctx (set by Layer 1: Interpreter),
    invokes TGPT CLI to produce a structured Workflow Plan Action,
    and enriches ctx.clean_message before it reaches the target LLM.

    - On success : ctx.clean_message is replaced with the TGPT workflow plan
                   and the original intent is appended for context continuity.
    - On failure  : ctx is returned unmodified; pipeline degrades gracefully.
    """
    skip, reason = _should_skip(ctx)

    if skip:
        log_event("TGPT_ORCH", f"Orchestration skipped — {reason}.")
        ctx.tgpt_workflow_plan = None
        ctx.mark_stage("tgpt_orchestrator_skipped")
        return ctx

    log_event("TGPT_ORCH", (
        f"Orchestrating intent='{ctx.intent}' → target='{ctx.target}' "
        f"[{len(ctx.clean_message)} chars]"
    ))

    orchestration_prompt = _build_orchestration_prompt(ctx)
    workflow_plan = await _invoke_tgpt(orchestration_prompt)

    if workflow_plan:
        original_intent = ctx.clean_message
        ctx.tgpt_workflow_plan = workflow_plan

        # V2 Phase 3: Manager-Worker Delegation
        # Detect sub-tasks and dispatch ephemeral workers
        delegated_results = []
        if engine:
            subtasks = _detect_delegatable_tasks(workflow_plan)
            if subtasks:
                log_event("TGPT_ORCH", f"Detected {len(subtasks)} delegatable sub-tasks. Spawning workers...")
                delegated_results = await _dispatch_workers(subtasks, ctx, engine)

        # Inject TGPT plan, worker results, and original intent
        context_parts = [workflow_plan]
        
        if delegated_results:
            context_parts.append("\n[WORKER EXECUTION RESULTS]")
            for res in delegated_results:
                context_parts.append(f"Task: {res.task_id} (Success: {res.success})\nOutput:\n{res.text}\n")
            context_parts.append("[END WORKER RESULTS]\n")

        context_parts.append(f"\n[ORIGINAL USER INTENT — Preserve for context continuity]\n{original_intent}")
        
        ctx.clean_message = "\n".join(context_parts)
        log_event("TGPT_ORCH", (
            f"Workflow plan injected ({len(workflow_plan)} chars). "
            f"Original intent preserved ({len(original_intent)} chars)."
        ))
    else:
        ctx.tgpt_workflow_plan = None
        log_event("TGPT_ORCH", "TGPT returned no output — proceeding with original intent unchanged.")

    ctx.mark_stage("tgpt_orchestrator")
    return ctx

async def ask_tgpt_for_error_advice(tool_result: str, tool_name: str, args: dict) -> str:
    """
    Called by the Analyzer (Layer 5) when an MCP tool fails.
    Asks TGPT for a short advice on how to fix a failing MCP tool.
    """
    prompt = (
        f"=======================================\n"
        f"[SYSTEM EXCEPTION REPORT: BANE PIPELINE]\n"
        f"=======================================\n"
        f"The autonomous AI execution loop just experienced a failure on MCP tool: '{tool_name}'.\n"
        f"Args used: {args}\n"
        f"Error/Traceback output:\n{tool_result}\n\n"
        f"Your task: Briefly analyze this error and provide an extremely short (2-3 sentences max) set of recommendations for the main AI to fix this.\n"
        f"Speak as a fellow AI helper team mate ('TGPT'). Do NOT write the final code, just provide the correct path/approach or explain what they did wrong.\n"
        f"Give a highly focused recommendation on how to bypass this specific error."
    )
    
    log_event("TGPT_ORCH", f"Asking TGPT for advice on failed tool '{tool_name}'...")
    advice = await _invoke_tgpt(prompt)
    if advice:
        log_event("TGPT_ORCH", "TGPT successfully generated error recovery advice.")
        return f"\n\n[LAYER 1.5 TGPT COLLABORATOR] 💡 {advice}"
    return ""


# ── V2 Phase 3: Delegation Helpers ──────────────────────────────────────────

def _detect_delegatable_tasks(plan: str) -> list[str]:
    """
    Parse the TGPT workflow plan and extract discrete sub-tasks
    suitable for worker delegation (e.g., 'RESEARCH:', 'FETCH:').
    Returns a list of task instruction strings.
    """
    subtasks = []
    # Look for explicit markers the orchestrator might generate
    # For now, simple regex looking for "SUBTASK: [instruction]" or similar
    import re
    matches = re.finditer(r'(?:SUBTASK|DELEGATE|RESEARCH|FETCH):\s*([^\n]+)', plan, re.IGNORECASE)
    for m in matches:
        instruction = m.group(1).strip()
        if instruction and len(instruction) > 10:
            subtasks.append(instruction)
    return subtasks


async def _dispatch_workers(tasks: list[str], ctx: PipelineContext, engine) -> list:
    """
    Spawn ephemeral workers for a list of task instructions concurrently.
    """
    import asyncio
    from pipeline.worker import EphemeralWorker, WorkerTask
    from core.command_router import router

    results = []
    worker = EphemeralWorker(engine, timeout=60.0)
    
    # Try to find available profiles, default to "Profile 8" if none available
    available_profiles = router.get_available_profiles() if hasattr(router, 'get_available_profiles') else []
    
    coros = []
    for i, instruction in enumerate(tasks):
        # Round-robin profile assignment if multiple available
        profile = available_profiles[i % len(available_profiles)] if available_profiles else "Profile 8"
        
        task = WorkerTask(
            goal=instruction,
            target_profile=profile,
            target_llm=ctx.target,
            parent_request_id=ctx.request_id,
            user_id=ctx.user_id,
            platform=ctx.platform
        )
        coros.append(worker.execute(task))

    if coros:
        if ctx.on_partial: await ctx.on_partial({"status": f"[L1.5] Spawning {len(coros)} background worker(s)..."})
        completed = await asyncio.gather(*coros, return_exceptions=True)
        for res in completed:
            if not isinstance(res, Exception):
                results.append(res)
                
    return results
