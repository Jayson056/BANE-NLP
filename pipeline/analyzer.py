"""
Pipeline Analyzer
==================
Stage 2: Analyze the request context — detect file presence,
compute metadata, and enrich the context.
"""

import os
from pipeline.context import PipelineContext
from core.logger import log_event


def run(ctx: PipelineContext) -> PipelineContext:
    """
    Analyze the request:
    - Determine if user attached files
    - Validate file paths exist
    - Flag file-related metadata
    """
    # Consolidate file paths
    valid_paths = [p for p in ctx.file_paths if os.path.exists(p)]
    ctx.file_paths = valid_paths

    # Check for user-uploaded content
    ctx.has_user_files = bool(ctx.file_paths) or bool(ctx.file_datas)

    # V2 Phase 2: Payload Size Validation (reject >10MB)
    MAX_PAYLOAD_SIZE = 10 * 1024 * 1024
    total_size = 0
    for file_data in ctx.file_datas:
        if "data" in file_data:
            total_size += len(file_data["data"])
    if total_size > MAX_PAYLOAD_SIZE:
        ctx.error = "❌ Request rejected: Total payload size exceeds 10MB."
        log_event("PIPELINE", f"[Analyzer] FAILED: Payload size {total_size} bytes exceeds 10MB limit.")
        ctx.mark_stage("analyzer")
        return ctx

    log_event("PIPELINE", f"[Analyzer] Files={len(ctx.file_paths)}, DataBlobs={len(ctx.file_datas)}, HasFiles={ctx.has_user_files}")
    ctx.mark_stage("analyzer")
    return ctx
