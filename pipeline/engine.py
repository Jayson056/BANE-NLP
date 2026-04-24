"""
Pipeline Engine (4-Layer Architecture)
======================================
Consolidated pipeline — merged from the original 8-layer design.
Eliminates unnecessary layer boundaries for <1ms operations.

Layers:
  L1   : INTAKE       (Intent Classification + Safety Guardrails)  — merged interpreter + guardrails
  L1.5 : TGPT ORCH.   (Optional Workflow Planning via tgpt CLI)    — kept separate (heavyweight)
  L2   : PLAN+COMPOSE (Target Resolution + Prompt Assembly)        — merged planner + composer
  L3   : EXECUTE      (Browser Bridge Dispatch + Response Capture)  — merged dispatcher + executor
         ANALYZE      (Tool Call Extraction + Autonomous Loop)      — inline in engine
  RETURN: Render + Deliver (post-processing, not a named layer)
"""

import asyncio
import re
import json
from typing import Optional, Callable, List, Dict, Any, Union

from pipeline.context import PipelineContext
from pipeline import intake, planner, composer, analyzer
from pipeline import bridge_executor
from pipeline.context_builder import build_context
from core.database import ensure_user, get_or_create_conversation, save_message, create_ai_session, complete_ai_session
from core.logger import log_event, log_error

class PipelineEngine:
    def __init__(self, bridge, response_handler, voice_engine):
        self.bridge = bridge
        self.response_handler = response_handler
        self.voice_engine = voice_engine
        self._browser_lock = asyncio.Lock()

    async def run(
        self,
        user_id: Union[str, int],
        message: str = "",
        target: Optional[str] = None,
        source: str = "Messenger",
        file_path: Optional[str] = None,
        file_paths: Optional[List[str]] = None,
        file_data: Optional[dict] = None,
        file_datas: Optional[List[dict]] = None,
        forced_filename: Optional[str] = None,
        on_partial: Optional[Callable] = None,
        generate_voice: bool = True,
        chrome_profile: str = "",
        voice_name: Optional[str] = None
    ) -> Union[str, dict]:
        
        ctx = PipelineContext(
            user_id=str(user_id),
            platform=source,
            raw_message=message,
            target=target or "chatgpt",
            file_paths=self._collect_paths(file_path, file_paths),
            file_datas=self._collect_datas(file_data, file_datas),
            forced_filename=forced_filename,
            on_partial=on_partial,
            chrome_profile=chrome_profile,
        )
        ctx.generate_voice = generate_voice
        ctx.voice_name = voice_name

        # ─── DATABASE SESSION MANAGEMENT ───
        try:
            # 1. Fetch/Create Universal DB User ID
            ctx.db_user_id = await asyncio.to_thread(ensure_user, ctx.platform, ctx.user_id)
            # 2. Get active conversation session
            ctx.conversation_id = await asyncio.to_thread(
                get_or_create_conversation, ctx.db_user_id, ctx.platform, chrome_profile=ctx.chrome_profile
            )
            # 3. Save incoming user message (only if there's text)
            if ctx.raw_message.strip():
                asyncio.create_task(asyncio.to_thread(save_message, ctx.conversation_id, "USER", ctx.raw_message.strip()))
        except Exception as e:
            log_error("DATABASE", f"Failed to log user session: {e}")

        log_event("ENGINE", f"⚡ Webhook Input [{ctx.request_id[:8]}] Source: {source} | Conv: {ctx.conversation_id}")

        try:
            # ─────────────────────────────────────────────────────────
            # LAYER 1: INTAKE (Intent + Guardrails — merged)
            # ─────────────────────────────────────────────────────────
            if ctx.on_partial: await ctx.on_partial({"status": "[L1] Analyzing request + safety checks... (Layer 1)"})
            ctx = intake.run(ctx)
            if not ctx.passed_guardrails:
                return ctx.error
            log_event("LAYER_1", f"Intake Output: Intent={ctx.intent}, Guardrails=PASSED")
            if ctx.on_partial: await ctx.on_partial({"status": f"[L1] ✓ Intent: {ctx.intent} — Guardrails passed (Layer 1)"})

            # ─────────────────────────────────────────────────────────
            # LAYER 1.5: TGPT ORCHESTRATOR (Intent → Workflow Plan)
            # ─────────────────────────────────────────────────────────
            if ctx.on_partial: await ctx.on_partial({"status": "[L1.5] TGPT orchestrating workflow plan... (Layer 1.5)"})
            from pipeline import tgpt_orchestrator
            # V2 Phase 3: Pass engine reference for worker delegation
            ctx = await tgpt_orchestrator.run(ctx, engine=self)
            tgpt_status = "plan generated" if ctx.tgpt_workflow_plan else "skipped (simple intent)"
            log_event("LAYER_1.5", f"TGPT Orchestrator: {tgpt_status}")
            if ctx.on_partial: await ctx.on_partial({"status": f"[L1.5] ✓ TGPT: {tgpt_status} (Layer 1.5)"})

            # ─────────────────────────────────────────────────────────
            # LAYER 2: PLAN + COMPOSE (Target Resolution + Prompt Assembly — merged)
            # ─────────────────────────────────────────────────────────
            if ctx.on_partial: await ctx.on_partial({"status": "[L2] Planning + composing prompt... (Layer 2)"})
            ctx = planner.run(ctx)
            if ctx.is_failed:
                return ctx.error
                
            # Build database context block before composing
            ctx.dynamic_context = build_context(ctx.conversation_id, max_history=8)
            
            # Composer builds the final prompt and payload
            ctx = composer.run(ctx) 
            log_event("LAYER_2", f"Plan+Compose Output: Target={ctx.target.upper()}, Prompt={len(ctx.final_prompt)} chars")
            if ctx.on_partial: await ctx.on_partial({"status": f"[L2] ✓ Target: {ctx.target.upper()} — Prompt composed (Layer 2)"})

            # ─── ADAPTIVE AUTONOMOUS LOOP (AI-Driven, No Fixed Cap) ───
            # The AI decides when the task is complete — not a hardcoded limit.
            # A safety ceiling prevents infinite loops, but under normal operation
            # the AI should finish well before hitting it.
            SAFETY_CEILING = 50      # Absolute max to prevent runaway loops
            turns = 0
            consecutive_errors = 0   # Track back-to-back failures for escalation
            consecutive_schema_failures = 0 # V2 Phase 2: Track consecutive schema validation failures
            total_errors = 0         # Track overall error count
            last_error_tool = None   # Track which tool keeps failing
            last_error_msg = None    # Track the last error message for dedup
            
            while turns < SAFETY_CEILING:
                # Check for manual termination from Telegram
                if getattr(self, "cancel_tokens", {}).get(ctx.user_id, False):
                    log_event("ENGINE", f"User {ctx.user_id} forcefully terminated the loop.")
                    ctx.response_text = "🛑 Task force-stopped by user."
                    break

                turns += 1
                
                # Reset stale state from previous iteration (critical for re-dispatch)
                ctx.raw_response = None
                ctx.error = None
                
                # ─────────────────────────────────────────────────────────
                # LAYER 3: BRIDGE EXECUTOR (Dispatch + Response — merged)
                # ─────────────────────────────────────────────────────────
                if getattr(self, "cancel_tokens", {}).get(ctx.user_id, False): break
                log_event("LAYER_3", f"BridgeExecutor: Dispatch to target {ctx.target}")
                if ctx.on_partial: await ctx.on_partial({"status": f"[L3] Connecting to {ctx.target.upper()} + waiting for response... (Layer 3)"})
                ctx = await bridge_executor.run(
                    ctx, self.bridge, self._browser_lock,
                    self.response_handler, self.voice_engine,
                    voice_name=ctx.voice_name
                )
                if getattr(self, "cancel_tokens", {}).get(ctx.user_id, False): break
                if ctx.is_failed:
                    if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ✗ Bridge execution failed — {ctx.error}"})
                    return ctx.error
                if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ✓ AI response captured ({len(ctx.response_text)} chars) (Layer 3)"})

                # ─────────────────────────────────────────────────────────
                # ANALYZE: Tool Call Extraction & Autonomous Loop
                # ─────────────────────────────────────────────────────────
                if getattr(self, "cancel_tokens", {}).get(ctx.user_id, False): break
                tool_data = None
                
                text = ctx.response_text
                text_for_analysis = re.sub(r'\[TOOL RESULT:.*?\[END TOOL RESULT\]', '', text, flags=re.DOTALL).strip()
                
                # Broad markdown and label stripping for cleaner JSON extraction
                text_clean = text_for_analysis.strip()
                text_clean = re.sub(r'```(?:json|javascript|js|python|code|plaintext|text|bash)?', '', text_clean, flags=re.IGNORECASE)
                text_clean = text_clean.replace('```', '')
                text_clean = re.sub(r'^(?:JSON|json|Javascript|javascript|python|Python|code|Code)[\s]*', '', text_clean.strip(), flags=re.IGNORECASE)
                text_clean = text_clean.strip()
                
                if "[ABORT TASK]" in text_clean:
                    log_event("LAYER_5", "AI voluntarily aborted the task loop.")
                    ctx.response_text = text_clean.replace("[ABORT TASK]", "").strip()
                    if not ctx.response_text:
                        ctx.response_text = "⚠️ Task aborted by AI due to an unrecoverable error or loop condition."
                    break

                # ── ROBUST JSON EXTRACTION ──
                # Instead of regex that breaks on nested braces, we scan the string 
                # for '{' and track depth to extract complete JSON objects.
                def extract_json_blocks(source_text: str) -> list[str]:
                    blocks = []
                    start_idx = 0
                    while True:
                        idx = source_text.find('{', start_idx)
                        if idx == -1: break
                        depth = 0
                        in_string = False
                        escape = False
                        end_pos = -1
                        for i in range(idx, len(source_text)):
                            c = source_text[i]
                            if not escape and c == '"':
                                in_string = not in_string
                            if not in_string:
                                if c == '{': depth += 1
                                elif c == '}': depth -= 1
                            if depth == 0:
                                end_pos = i + 1
                                break
                            escape = (c == '\\' and not escape)
                        
                        if end_pos != -1:
                            blocks.append(source_text[idx:end_pos])
                            start_idx = end_pos
                        else:
                            start_idx = idx + 1
                    return blocks

                found_tools = []
                # 1. Extract ALL valid JSON tool calls safely
                all_blocks = extract_json_blocks(text_for_analysis)
                for block in all_blocks:
                    if '"call_tool"' in block or '"action"' in block or '"tool"' in block:
                        try:
                            data = json.loads(block)
                            
                            # Normalize Gemini formats to BNP format
                            if "action" in data and "call_tool" not in data:
                                data["call_tool"] = data["action"]
                            if "tool" in data and "call_tool" not in data:
                                data["call_tool"] = data["tool"]
                            if "details" in data and "args" not in data:
                                data["args"] = data["details"]
                            if "parameters" in data and "args" not in data:
                                data["args"] = data["parameters"]

                            if "call_tool" in data:
                                # ── NEW: Robust top-level arg detection ──
                                # If args/details/parameters is missing, treat all other keys as args
                                if "args" not in data or not data["args"]:
                                    args = {}
                                    for k, v in data.items():
                                        if k not in ["call_tool", "tool", "mcp_type", "action", "description", "details", "parameters", "thought", "reasoning"]:
                                            args[k] = v
                                    if args:
                                        data["args"] = args
                                    else:
                                        data["args"] = {}
                                
                                # V2 Phase 2: Schema Validation
                                from pipeline.tool_schema import validate_tool_call, sanitize_tool_call
                                from mcp_custom.mcp_registry import registry
                                
                                is_valid, reason = validate_tool_call(data, set(registry.tools.keys()))
                                if is_valid:
                                    clean_data = sanitize_tool_call(data)
                                    found_tools.append(clean_data)
                                    consecutive_schema_failures = 0
                                else:
                                    # Inject schema failure back for self-correction
                                    consecutive_schema_failures += 1
                                    log_event("SCHEMA", f"Tool call validation failed: {reason}")
                                    if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ✗ Schema Validation Failed: {reason}"})
                                    
                                    # Construct feedback for schema failure
                                    schema_error_msg = f"[SCHEMA VALIDATION FAILED]\nYour tool call was invalid: {reason}\nPlease fix the tool name or format and try again."
                                    
                                    # We skip further extraction and jump to feedback construction
                                    # By setting found_tools to empty but consecutive_schema_failures > 0,
                                    # we trigger the retry logic below.
                                    found_tools = [] 
                                    batch_results = [f"--- [SCHEMA ERROR] ---\n{schema_error_msg}"]
                                    combined_is_error = True
                                    break
                        except:
                            # Try the repair fallback if direct parse failed
                            repaired = self._repair_tool_json(block)
                            if repaired:
                                # V2 Phase 2: Validate repaired data too
                                from pipeline.tool_schema import validate_tool_call, sanitize_tool_call
                                from mcp_custom.mcp_registry import registry
                                is_valid, reason = validate_tool_call(repaired, set(registry.tools.keys()))
                                if is_valid:
                                    found_tools.append(sanitize_tool_call(repaired))
                                    consecutive_schema_failures = 0

                # 2. Check for Hallucinated JSON in raw text (failsafe)
                if not found_tools and consecutive_schema_failures == 0 and ('"call_tool"' in text_clean or '"action"' in text_clean):
                     repaired = self._repair_tool_json(text_clean)
                     if repaired:
                         from pipeline.tool_schema import validate_tool_call, sanitize_tool_call
                         from mcp_custom.mcp_registry import registry
                         is_valid, reason = validate_tool_call(repaired, set(registry.tools.keys()))
                         if is_valid:
                             found_tools.append(sanitize_tool_call(repaired))

                # V2 Phase 2: Abort if stuck in a schema validation failure loop
                if consecutive_schema_failures >= 3:
                    log_event("ANALYZE", "Aborting task due to 3 consecutive schema validation failures.")
                    ctx.response_text = "❌ Task aborted: AI repeatedly generated malformed tool calls."
                    break

                # 3. Stop if no tools found (Task Complete)
                # UNLESS we just had a schema failure, in which case we must loop back to fix it
                if not found_tools and consecutive_schema_failures == 0:
                    log_event("ANALYZE", f"Task Complete after {turns} iterations ({total_errors} errors encountered).")
                    break 
                
                # 4. Sequential BATCH EXECUTION (only if we have tools and no immediate schema error)
                if found_tools:
                    batch_results = []
                    combined_is_error = False
                    processed_count = 0
                    
                    from mcp_custom.mcp_registry import registry
                    
                    for idx, tool_data in enumerate(found_tools):
                        tool_name = tool_data.get("call_tool")
                        args = tool_data.get("args", {})
                        
                        if not tool_name or tool_name in ("tool_name", "tool_name_here", "example_tool", ""):
                            continue
                            
                        # Fuzzy resolution
                        actual_tool_name = self._fuzzy_resolve_tool(tool_name, registry.tools) or tool_name
                        
                        log_event("ANALYZE", f"Batch Execution [{idx+1}/{len(found_tools)}]: {actual_tool_name}")
                        if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ⚙ TOOL [{idx+1}/{len(found_tools)}]: {actual_tool_name}..."})
                        
                        try:
                            tool_result = await asyncio.wait_for(registry.execute_tool(actual_tool_name, args), timeout=60)
                        except asyncio.TimeoutError:
                            tool_result = f"⚠️ Tool '{actual_tool_name}' timed out (60s)."
                        except Exception as e:
                            import traceback
                            full_trace = traceback.format_exc()
                            tool_result = f"❌ Execution error: {e}\n\nTraceback:\n{full_trace}"

                        is_error = self._is_tool_error(tool_result)
                        if is_error:
                            combined_is_error = True
                            consecutive_errors += 1
                            total_errors += 1
                            last_error_tool = actual_tool_name
                            if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ✗ TOOL FAILED: {actual_tool_name} — {str(tool_result)[:80]}"})
                        else:
                            consecutive_errors = 0
                            if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ✓ TOOL OK: {actual_tool_name}"})
                            
                        batch_results.append(f"--- [BATCH ITEM {idx+1}: {actual_tool_name}] ---\n{tool_result}")
                        processed_count += 1
                else:
                    # We are here because consecutive_schema_failures > 0
                    # batch_results and combined_is_error are already set in the extraction loop
                    processed_count = 0
                    actual_tool_name = "hallucinated_tool" # Fallback for feedback builder
                    args = {} # Fallback for feedback builder

                # 5. Compile Feedback
                final_tool_result = "\n\n".join(batch_results)
                
                # Build the feedback block (using the last tool's metadata for the directive logic)
                status_block, directive = await self._build_adaptive_feedback(
                    is_error=combined_is_error,
                    tool_name=actual_tool_name,
                    args=args if 'args' in locals() else {},
                    tool_result=final_tool_result,
                    turns=turns,
                    consecutive_errors=consecutive_errors,
                    total_errors=total_errors,
                    last_error_tool=last_error_tool,
                )
                
                tool_result_content = (
                    f"BATCH EXECUTION COMPLETE ({processed_count} tools processed)\n"
                    f"{final_tool_result}\n\n"
                    f"{status_block}\n"
                    f"{directive}"
                )
                
                ctx.tool_results.append({
                    "tool": f"BATCH ({processed_count})",
                    "result": final_tool_result,
                    "status": status_block,
                    "directive": directive
                })
                
                tool_result_prompt = (
                    f"═══ MESSAGE SOURCE ═══\n"
                    f"FROM: {ctx.platform.upper()}\n"
                    f"USER_ID: {ctx.user_id}\n"
                    f"RESPOND VIA: {ctx.platform.upper()} delivery pipeline\n"
                    f"═══════════════════════\n"
                    "[KNOWLEDGE BASE] BANE_CONTEXT_FILES/BANE_NLP_BRAIN_knowledge.md\n"
                    "[COMMAND_MODE: AUTONOMOUS_ITERATION]\n"
                    f"[USER_ID: {ctx.user_id}]\n"
                    "\n[SYSTEM NOTICE] Tool execution result provided below. Follow rules and proceed with NEXT TOOL CALL or FINAL RESPONSE.\n"
                    f"USER: {tool_result_content}"
                )
                
                # Cleanup temp files before next iteration to avoid bloat
                ctx.file_paths, ctx.file_datas, ctx.has_user_files = [], [], False
                
                log_event("ANALYZE", f"Adaptive Loop: Re-dispatching iteration {turns} (errors: {consecutive_errors}/{total_errors})...")
                if ctx.on_partial: await ctx.on_partial({"status": f"[L3] ↻ Feeding results back → iter {turns+1} (errors: {total_errors})"})
                
                from pipeline.payload_builder import build_payload
                ctx.final_prompt = tool_result_prompt
                ctx.payload = build_payload(
                    message=tool_result_prompt,
                    target=ctx.target,
                    source=ctx.platform,
                    files=None,
                    chrome_profile=ctx.chrome_profile
                )
                ctx.request_id = ctx.payload.get("id", ctx.request_id)
            
            # ── Safety ceiling hit ──
            if turns >= SAFETY_CEILING:
                log_event("ENGINE", f"⚠️ Safety ceiling ({SAFETY_CEILING}) reached. Force-ending loop.")
                if not ctx.response_text or ctx.response_text.strip() == "":
                    ctx.response_text = f"⚠️ Task reached the safety limit of {SAFETY_CEILING} iterations without resolution. Please simplify the request or try again."

            # ─────────────────────────────────────────────────────────
            # RETURN: Render + Deliver (post-processing)
            # ─────────────────────────────────────────────────────────
            if ctx.on_partial: await ctx.on_partial({"status": "[RET] Finalizing response... (Return)"})
            
            # Apply renderer to clean the final output before sending to the user
            ctx.response_text = self._render_response(ctx.response_text)
            
            # Database session update (save final AI response)
            try:
                if ctx.response_text and ctx.response_text.strip():
                    asyncio.create_task(asyncio.to_thread(save_message, ctx.conversation_id, "AI", ctx.response_text.strip()))
            except Exception as e:
                log_error("DATABASE", f"Failed to log AI response to database: {e}")
                
            log_event("RETURN", f"Rendered response ({len(ctx.response_text)} chars) → {ctx.platform.upper()}")
            
            return {
                "text": ctx.response_text,
                "suggestions": ctx.suggestions,
                "audio_path": ctx.audio_path,
                "images": ctx.images,
                "videos": ctx.videos,
                "files": ctx.files,
                "request_id": ctx.request_id,
                "target": ctx.target,
            }

        except asyncio.CancelledError:
            log_event("ENGINE", f"Task for User {ctx.user_id} was CANCELLED via kill-switch.")
            raise # RE-RAISE to ensure parent task effectively stops
        except Exception as e:
            log_error("ENGINE", e)
            return f"❌ Pipeline error: {e}"

    def _is_tool_error(self, result: str) -> bool:
        """Detect whether a tool result represents an error/failure."""
        if result is None:
            return True
        
        # An empty string is often a success for shell redirection or empty lists
        if result == "":
            return False
        
        error_indicators = [
            "❌",                    # Our explicit error prefix
            "⚠️",                    # Warning/timeout prefix
            "Error:",               # Generic error
            "error:",               # Lowercase variant
            "Error executing",      # From command_tools exception handler
            "Exception:",           # Python exceptions
            "Traceback",            # Python stack traces
            "FAILED",               # Explicit failure
            "not found",            # Missing resources
            "Permission denied",    # Access errors
            "No such file",         # File not found
            "Tool execution failed", # From mcp_registry.execute_tool
        ]
        
        # Check first 500 chars for error indicators (errors are at the start)
        check_region = result[:500]
        return any(indicator in check_region for indicator in error_indicators)

    async def _build_adaptive_feedback(
        self,
        is_error: bool,
        tool_name: str,
        args: dict,
        tool_result: str,
        turns: int,
        consecutive_errors: int,
        total_errors: int,
        last_error_tool: str | None,
    ) -> tuple[str, str]:
        """Build escalating status block and directive based on error severity.
        
        Returns:
            (status_block, directive) — both strings injected into the feedback prompt.
        
        Escalation Tiers:
            Tier 0: SUCCESS — clean pass-through
            Tier 1: First error — standard retry prompt
            Tier 2: 2-3 consecutive errors — provide system diagnostics hints
            Tier 3: 4-6 consecutive errors — stern warning, force alternative approach
            Tier 4: 7+ consecutive errors — final warning, strongly suggest abort
        """
        if not is_error:
            # ── Tier 0: SUCCESS ──
            status_block = "[EXECUTION STATUS: SUCCESS]"
            directive = (
                f"BANE: Iteration {turns} complete. You have unlimited iterations to get this right.\n\n"
                f"🚨 MANDATORY: If the task requires further tools (e.g. creating more files, running commands), you MUST respond with ONLY THE NEXT JSON TOOL CALL and NOTHING ELSE.\n"
                f"❌ DO NOT narrate your progress. DO NOT provide status updates. DO NOT say 'I am proceeding'.\n"
                f"✅ ONLY provide your final human-readable response once the task is 100% PHYSICALLY COMPLETE on the host system."
            )
            return status_block, directive
        
        # ── Base error status block (shared across all error tiers) ──
        status_block = (
            f"[EXECUTION STATUS: FAILED]\n"
            f"⚠️ The tool returned an error. DO NOT claim success.\n"
            f"Passed args were: {json.dumps(args)}"
        )
        
        if consecutive_errors <= 1:
            # ── Tier 1: First error — standard retry ──
            directive = (
                f"BANE: Iteration {turns} — tool failed. You have unlimited retries.\n"
                f"READ the error message carefully. Fix the args or approach and retry.\n"
                f"DO NOT repeat the exact same failing command. Analyze WHY it failed.\n"
            )
            
            # Specific hint for newline escaping & name variables
            if "SyntaxError" in tool_result:
                if "\\n" in tool_result or "\\n" in str(args):
                    directive += "CRITICAL: You wrote literal '\\n' characters into the file instead of real newlines. RE-WRITE THE FILE using actual newlines (hit enter key) in your JSON content string.\n"
                elif "'name' is not defined" in tool_result:
                    directive += "CRITICAL: You used 'name' instead of '__name__'. Re-write the code with correct Python standard variables.\n"
            
            directive += "DO NOT claim success. Either fix it or explain the failure to the user."
        
        elif consecutive_errors <= 3:
            # ── Tier 2: Recurring error — provide diagnostic hints ──
            directive = (
                f"BANE: Iteration {turns} — {consecutive_errors} consecutive errors on '{last_error_tool}'.\n"
                f"⚠️ You are repeating failures. STOP and think differently.\n\n"
                f"DIAGNOSTIC HINTS:\n"
                f"• OS: Windows. Shell: cmd.exe (via subprocess). Use Windows syntax.\n"
                f"• For 'start' commands: use full path or ensure the program is in PATH.\n"
                f"• Chrome profiles are at: %LOCALAPPDATA%\\Google\\Chrome\\User Data\\Profile N\n"
                f"• Use 'command_tools.run_command' with the 'command' arg as a string.\n"
                f"• If a file/path doesn't exist, use file_tools.list_dir to explore first.\n"
                f"• Try a COMPLETELY different approach to solve the same problem.\n\n"
                f"Fix the root cause. DO NOT retry the same broken command."
            )
        
        elif consecutive_errors <= 6:
            # ── Tier 3: Persistent failure — stern warning ──
            directive = (
                f"BANE: ⚠️ CRITICAL — {consecutive_errors} consecutive failures ({total_errors} total).\n"
                f"You are stuck in a failure loop on '{last_error_tool}'.\n\n"
                f"MANDATORY ACTIONS:\n"
                f"1. STOP using '{last_error_tool}' with the same args.\n"
                f"2. Use a diagnostic tool first (e.g., file_tools.list_dir, system_tools.get_sys_info) to understand the system state.\n"
                f"3. Try a fundamentally different approach.\n"
                f"4. If the task genuinely cannot be done, tell the user honestly WHY — no assumptions.\n\n"
                f"If the same tool fails again, output \"[ABORT TASK]\" with an honest explanation."
            )
        
        else:
            # ── Tier 4: Critical failure — final warning before abort ──
            directive = (
                f"BANE: 🚨 FINAL WARNING — {consecutive_errors} consecutive failures.\n"
                f"You have exhausted reasonable retries for '{last_error_tool}'.\n\n"
                f"You MUST do ONE of these:\n"
                f"1. Use a COMPLETELY different tool or strategy (not '{last_error_tool}').\n"
                f"2. Output \"[ABORT TASK]\" followed by an honest explanation of what failed and why.\n\n"
                f"DO NOT retry the same approach. DO NOT hallucinate success."
            )
        
        # ── INTERCEPT & COLLABORATE: Ask TGPT Pipeline for Advice ──
        if consecutive_errors >= 1:
            try:
                from pipeline.tgpt_orchestrator import ask_tgpt_for_error_advice
                # We specifically pass the last error's details so TGPT can diagnose
                tgpt_help = await ask_tgpt_for_error_advice(tool_result, last_error_tool, args)
                if tgpt_help:
                    directive += tgpt_help
            except Exception as e:
                log_error("ENGINE", f"Failed to fetch TGPT advice: {e}")

        return status_block, directive

    def _render_response(self, text: str) -> str:
        """
        Layer 7: Strip system-only instructions, tool documentation, 
        and injection headers to return ONLY human-readable content.
        """
        if not text: return ""
        log_event("RENDERER", f"Rendering input: {len(text)} chars | Text preview: {text[:50]}...")
        
        # 1. Strip Metadata & Heavy Headers
        text = re.sub(r'\[MANDATORY RULES\] MANDATORY_RULES\.txt', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[WORKSPACE MAP\] WORKSPACE_ARCHITECTURE\.md', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[PROJECT CONTEXT\] ACTIVE_PROJECTS_CONTEXT\.md', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[SCENARIOS GUIDE\] BANE_SCENARIOS\.md', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[DEPLOYMENT_GUIDE\] AUTONOMOUS_DEPLOYMENT_GUIDE\.md', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[MCP_TOOL_GUIDE\] MCP_TOOLS_DOCUMENTATION\.md', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[EXECUTION COMMAND\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[COMMAND_MODE: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[PLATFORM: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[USER_ID: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[CHROME_PROFILE: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[TARGET: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[MASTER PROFILE ACTIVE: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[AUTHORITY: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[CHROME_PROFILE_SYSTEM\][^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[PROFILE: [\s\S]*?\]', '', text, flags=re.IGNORECASE)
        
        # 1c. Strip Source Identification Block (multi-platform routing header)
        text = re.sub(r'═══ MESSAGE SOURCE ═══.*?═══════════════════════', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'^FROM: (?:TELEGRAM|MESSENGER|PORTFOLIO).*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^RESPOND VIA:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        # 1b. Strip AI-generated Status Headers (Fix for Telegram "cramped" feel)
        text = re.sub(r'^System Status:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^🟢 Platform:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^🟢 User: Authorized.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        text = re.sub(r'^USER:.*$', '', text, flags=re.MULTILINE).strip()
        
        # 1b. Strip Custom Gem UI artifacts (BANE-NLP • Custom Gem header, Sources label)
        text = re.sub(r'^(?:B\s*)?BANE-NLP\s*[•·]?\s*Custom Gem\s*(?:Analysis\s*)?', '', text, flags=re.IGNORECASE | re.MULTILINE).strip()
        text = re.sub(r'^(?:B\s*)?BANE-NLP\s*(?:said)?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE).strip()
        text = re.sub(r'^\s*said\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE).strip()
        text = re.sub(r'^\s*Sources\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE).strip()
        
        # 1d. Strip Gemini Custom Gem "Analysis" / "Query successful" UI artifacts
        # These leak from the collapsible analysis panel in Gemini's Custom Gem interface
        text = re.sub(r'^\s*Analysis\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE).strip()
        text = re.sub(r'^\s*[✓✔☑︎]\s*(?:Query|Analysis)\s+successful\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE).strip()
        text = re.sub(r'^\s*[-•–]\s*Query successful\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE).strip()
        text = re.sub(r'^\s*Query successful\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE).strip()
        text = re.sub(r'^\s*Analyzing\.{0,3}\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE).strip()
        
        # 2. Strip System Tool Docs (New Slim Version)
        # (Removed dangerous SYSTEM TOOLS stripping rule that was too aggressive)
        
        # 3. Strip old context artifacts
        text = re.sub(r'\[TOOL RESULT:.*?\[END TOOL RESULT\]', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # 3b. Strip execution status markers and BANE feedback directives
        text = re.sub(r'\[EXECUTION STATUS: \w+\]', '', text, flags=re.IGNORECASE)
        
        text = re.sub(r'^.*?BANE: Iteration \d+ complete\..*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?BANE: Iteration \d+ — tool failed\..*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?BANE: Iteration \d+ — \d+ consecutive errors.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?BANE: ⚠️ CRITICAL — .*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?BANE: 🛑 ABORTING —.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        text = re.sub(r'^.*?You have unlimited iterations to get this right\..*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?You have unlimited retries\..*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?If the task requires further steps.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?If the task is 100% complete.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?DO NOT assume or hallucinate results.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        text = re.sub(r'^.*?⚠️ The tool returned an error.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?Passed args were:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?READ the error message carefully.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?DO NOT repeat the exact same failing command.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?DO NOT claim success.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'^.*?If you encounter repeated errors and cannot proceed.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        text = re.sub(r'DIAGNOSTIC HINTS:[\s\S]*?Fix the root cause\..*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'MANDATORY ACTIONS:[\s\S]*?output "\[ABORT TASK\]".*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 4. JSON Extraction (Strip raw JSON if AI echoed tool result, but NEVER strip tool calls)
        json_data = self._extract_json(text)
        if json_data and not json_data.get("call_tool"):
            output = json_data.get("output") or json_data.get("message") or json_data.get("response")
            if output:
                log_event("RENDERER", "Successfully stripped JSON payload; extracted 'output' field.")
                return str(output).strip()
        
        # 4b. FAILSAFE: Strip any leaked call_tool JSON that the pipeline didn't execute
        # This catches cases where the AI outputted a JSON tool call but the tool wasn't recognized
        text = self._strip_tool_json(text)
        
        # 5. Final polish
        final_text = text.strip()
        log_event("RENDERER", f"Rendering complete: {len(final_text)} chars")
        return final_text

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Attempt to find and parse a JSON block from text."""
        # Try finding markdown block first
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            try: return json.loads(match.group(1))
            except: pass
        
        # Try raw braces
        text_clean = re.sub(r'^(?:JSON|json|Javascript|javascript|python|Python|code|Code)\s*', '', text.strip())
        if text_clean.startswith("{") and text_clean.endswith("}"):
            try: return json.loads(text_clean)
            except: pass
            
        return None

    def _repair_tool_json(self, text: str) -> Optional[Dict]:
        """
        Repair malformed call_tool JSON when escape sequences are lost.
        
        Root cause: Content scripts capture via innerText/textContent,
        which renders \" as bare ". This makes json.loads() fail on strings
        containing quotes (e.g. command-line args with --profile="Profile 4").
        
        Strategy:
          1. Extract the tool name (always clean — simple string value)
          2. Extract args block boundaries via brace counting
          3. For each arg key, greedily extract the value (tolerating inner quotes)
        """
        try:
            # Step 1: Extract tool name — always parseable since it's a simple string
            name_match = re.search(r'"(?:call_tool|action)"\s*:\s*"([^"]+)"', text)
            if not name_match:
                return None
            tool_name = name_match.group(1)
            
            # Step 2: Find the args object boundaries
            args_match = re.search(r'"(?:args|details|parameters)"\s*:\s*\{', text)
            if not args_match:
                # ── NEW: Failsafe for top-level args ──
                # If no explicit args object, try to extract keys from the top level
                try:
                    # Strip call_tool/action/description from the raw block
                    temp_data = json.loads(text) if "{" in text and "}" in text else {}
                    if temp_data:
                         args = {k: v for k, v in temp_data.items() if k not in ["call_tool", "action", "description", "details", "parameters"]}
                         return {"call_tool": tool_name, "args": args}
                except:
                    pass
                return {"call_tool": tool_name, "args": {}}
            
            args_start = args_match.end()
            
            # Find the matching closing brace by counting depth
            depth = 1
            pos = args_start
            while pos < len(text) and depth > 0:
                if text[pos] == '{': depth += 1
                elif text[pos] == '}': depth -= 1
                pos += 1
            
            if depth != 0:
                return {"call_tool": tool_name, "args": {}}
            
            args_inner = text[args_start:pos-1].strip()
            
            # Step 3: Try to parse the args as-is first (handles empty args {})
            if not args_inner:
                return {"call_tool": tool_name, "args": {}}
            
            try:
                args = json.loads("{" + args_inner + "}")
                return {"call_tool": tool_name, "args": args}
            except:
                pass
            
            # Step 4: Iterative key-value extraction for args (resilient to unescaped quotes)
            keys = list(re.finditer(r'"(\w+)"\s*:', args_inner))
            if not keys:
                log_event("LAYER_5", f"⚠️ JSON Repair: Fell back to EMPTY args for {tool_name}. The original command args were lost during DOM capture.")
                return {"call_tool": tool_name, "args": {}}
                
            args = {}
            for i in range(len(keys)):
                key = keys[i].group(1)
                val_start = keys[i].end()
                if i + 1 < len(keys):
                    val_end = keys[i+1].start()
                    val_str = args_inner[val_start:val_end].strip()
                    if val_str.endswith(','):
                        val_str = val_str[:-1].strip()
                else:
                    val_str = args_inner[val_start:].strip()
                
                # Strip framing unescaped quotes inside
                if val_str.startswith('"') and val_str.endswith('"'):
                    val_str = val_str[1:-1]
                
                # Unescape common sequences that get literal-encoded by DOM capture
                if "\\" in val_str:
                    val_str = val_str.replace("\\n", "\n").replace("\\\"", "\"").replace("\\\\", "\\").replace("\\t", "\t")
                
                # 🔥 POST-CAPTURE REPAIR: Handle literal newlines and tabs if they were injected by the scraper
                # This fixes "unterminated string literal" issues.
                if "\n" in val_str or "\t" in val_str or "<b>" in val_str:
                    val_str = val_str.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
                    # If we find actual newlines, we keep them because the AI likely intended them as block content
                    # But we ensure they are clean.
                
                args[key] = val_str
                
            return {"call_tool": tool_name, "args": args}
        except Exception:
            return None

    @staticmethod
    def _fuzzy_resolve_tool(hallucinated_name: str, tool_registry: dict) -> Optional[str]:
        """Attempt to fuzzy-match a hallucinated tool name to an actual registered tool.
        
        Strategy:
          1. Check common aliases.
          2. Normalize both names by stripping underscores, dots, hyphens, and lowering.
          3. If exact normalized match → return the real tool name.
          4. If partial containment match (e.g. 'sendtelegrammessage' in 'communication_tools.send_telegram_message') → return.
          
        Returns:
            The actual registered tool name, or None if no match found.
        """
        def normalize(name: str) -> str:
            return name.replace("_", "").replace(".", "").replace("-", "").lower()
        
        name_lower = hallucinated_name.lower()
        
        # Common hallucination mappings
        ALIASES = {
            "list_directory": "file_tools.list_dir",
            "list_files": "file_tools.list_dir",
            "read_file": "file_tools.read_file",
            "write_file": "file_tools.write_file",
            "create_file": "file_tools.write_file",
            "run_command": "command_tools.run_command",
            "execute_command": "command_tools.run_command",
            "shell": "command_tools.run_command",
            "screenshot": "desktop_tools.screenshot",
        }
        if name_lower in ALIASES and ALIASES[name_lower] in tool_registry:
            return ALIASES[name_lower]
        
        target_norm = normalize(hallucinated_name)
        
        # Exact normalized match
        for real_name in tool_registry:
            if normalize(real_name) == target_norm:
                return real_name
        
        # Partial match: check if the hallucinated name's method part matches
        method_part = target_norm.split(".")[-1] if "." in hallucinated_name else target_norm
        for real_name in tool_registry:
            real_norm = normalize(real_name)
            real_parts = real_name.split('.')
            real_method = normalize(real_parts[-1])
            
            if method_part == real_method or method_part in real_method or real_method in method_part:
                return real_name
        
        return None

    @staticmethod
    def _strip_tool_json(text: str) -> str:
        """Remove any raw call_tool JSON blocks from text.
        
        This prevents pipeline-internal JSON from leaking to the user.
        Replaces the JSON with a clean user-facing message indicating
        the command was processed.
        """
        if not text or ('"call_tool"' not in text and '"action"' not in text):
            return text
        
        import re
        
        # Strip markdown-wrapped JSON blocks containing call_tool or action
        text = re.sub(
            r'```(?:json)?\s*\{[^}]*"(?:call_tool|action)"[^}]*\}\s*```',
            '',
            text,
            flags=re.DOTALL | re.IGNORECASE
        )
        
        # Strip raw JSON blocks containing call_tool (brace-balanced extraction)
        # We need to be careful not to strip partial text, so we re-use extract logic
        lines = text.split('\n')
        cleaned_lines = []
        skip = False
        brace_depth = 0
        json_buffer = ""
        
        for line in lines:
            if not skip and '{' in line and ('"call_tool"' in line or '"action"' in line):
                skip = True
                brace_depth = 0
                json_buffer = ""
            
            if skip:
                json_buffer += line + "\n"
                brace_depth += line.count('{') - line.count('}')
                if brace_depth <= 0:
                    skip = False
                    # Don't add this JSON block to output
                continue
            
            cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        # If stripping left us with nothing, provide a fallback
        if not result or len(result) < 5:
            result = "⚙️ Command processed internally."
        
        return result

    @staticmethod
    def _collect_paths(single, multi):
        paths = []
        if single: paths.append(single)
        if multi: paths.extend(multi)
        return paths

    @staticmethod
    def _collect_datas(single, multi):
        datas = []
        if single: datas.append(single)
        if multi: datas.extend(multi)
        return datas
