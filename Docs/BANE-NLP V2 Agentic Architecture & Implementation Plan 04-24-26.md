# BANE-NLP V2: Agentic Architecture & Implementation Plan

**Lead Engineer:** Jayson Apable Combate
**Status:** Architecture Upgrade & Multi-Agent Transition

This document provides a comprehensive breakdown of the BANE-NLP system, detailing its upgraded structure, technology stack, and the structured implementation roadmap for transitioning into a high-speed, professional-grade Agentic AI orchestrator.

---

## 1. System Overview & Tech Stack

**BANE-NLP** (Bane Notebook Pipeline) is an autonomous execution agent acting as a bridge between messaging platforms (Telegram, Messenger) and web-based LLMs (Google Gemini, Google NotebookLM, OpenAI ChatGPT). The V2 architecture shifts BANE-NLP from a "command-executor" to a continuous "goal-orchestrator."

### Technology Stack
* **Backend / Orchestration:** Python 3 (`asyncio` for non-blocking operations).
* **C-Backend (Proxy/Security):** C (winsock2) for a lightweight webhook server proxy (`bane_server.c`), compiled using the **ming GWLVM** compiler to ensure header file stability.
* **WebSockets:** Bidirectional communication between the Python backend and the Chrome Extension.
* **Browser Automation/Bridge:** Chrome Extension (Manifest V3) running persistent background service workers.
* **Database:** SQLite (`bane_data.db`) with WAL mode for fast, concurrent access.
* **Voice Engine:** `edge-tts` (Microsoft Edge Text-to-Speech) and `ffmpeg`.

---

## 2. Advanced Agentic Logic & Multi-Agent Orchestration

A professional agent collaboratively navigates complex goals through autonomous tool usage in a continuous loop.

* **Goal-Driven Evolution:** Users provide broad objectives instead of specific commands. The system autonomously analyzes, acts, observes, and iterates until the goal is achieved.
* **Manager-Worker Pattern:**
    * **The Manager (`tgpt_orchestrator.py`):** Holds the high-level plan and state. It delegates tasks but lacks direct browsing tools to prevent context pollution.
    * **Ephemeral Workers (`core/command_router.py`):** Spawned into isolated Chrome profiles (e.g., Profile 2 or 3) with narrow, site-specific goals. Once finished, the worker returns clean data and terminates, clearing its context.
* **Self-Evolution (Dynamic Tooling):** Operationalize `meta_tools.create_tool` to allow BANE-NLP to write and hot-reload its own Python code when encountering unknown challenges.

---

## 3. High-Performance Context Engineering

To eliminate the noise of standard HTML extraction, BANE-NLP utilizes advanced semantic compression to optimize token usage and accelerate reasoning.

* **Semantic Compression (AxTree):** Raw DOM extraction via `content_gemini.js` is replaced with the Accessibility Tree (AxTree). 
    * By utilizing the Chrome DevTools Protocol (`chrome.debugger.attach` and `Accessibility.getFullAXTree`), BANE-NLP strips presentation layers (nested divs, CSS) and extracts a pure semantic map of Roles, Names, and States. This yields up to a 10x token reduction.
* **Focused Chain-of-Thought (F-CoT):** Explicit separation of information extraction and reasoning. The Extraction Layer pulls essential facts into structured XML, and the Reasoning Layer queries only that structured context.
* **Tiered State Management (`pipeline/context.py`):** * **JIT Context:** Context is dynamically loaded via tool searches only when required.
    * **Context Compaction:** When SQLite conversational history reaches 70% of the token limit, an LLM-based compaction step distills the history into a high-fidelity summary, discarding verbose `[TOOL RESULT]` outputs.

---

## 4. Transaction Speed & Infrastructure Optimization

Professional systems eliminate artificial delays to provide real-time interaction.

* **The C-Backend "Gatekeeper":** The native `bane_server.c` webhook router provides maximum throughput and minimal latency for high-frequency platforms like Messenger. 
* **Polling & Sync Optimization:** WebSockets in `background.js` and `browser_bridge.py` are optimized. `setTimeout` and polling intervals are reduced from 500ms to 50ms–100ms for instant dispatch and response capture.
* **Bulk Interaction Actions:** Independent browser actions (e.g., clicking, typing into multiple fields) are grouped into a single tool call to reduce execution time and token consumption.

---

## 5. Proactive Security & Observability

Autonomous agents must operate within deterministic safety boundaries.

* **Deterministic Guardrails (Schema Gate):** Layer 6 (`pipeline/analyzer.py`) enforces strict JSON Schema validation (via Python `jsonschema` or `pydantic`) for every tool call. Malformed arguments or hallucinated fields are automatically rejected before reaching the OS layer.
* **Parent-Child Security Model:** A privileged Parent context binds Inter-Process Communication (IPC) tunnels to internal APIs, ensuring commands are delivered into a sandboxed environment validated against an allowlist.
* **Full-Stack Observability:** Distributed tracing logs the internal monologue of the agent (tool selections, document retrievals), tracking Context Recall and Faithfulness to catch hallucinations early.

---

## 6. Implementation Roadmap

| Phase | Focus Area | Key Actions | Target Files |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Speed** | Deploy C-Backend proxy built with ming GWLVM; optimize WebSocket polling intervals to <100ms. | `bane_server.c`, `background.js`, `browser_bridge.py` |
| **Phase 2** | **Safety** | Enforce Strict JSON Schema validation and Parent-Child isolation to lock down the execution loop. | `analyzer.py`, `mcp_registry.py` |
| **Phase 3** | **Agency** | Implement Manager-Worker multi-agent pattern; isolate task delegation across Chrome profiles. | `tgpt_orchestrator.py`, `command_router.py` |
| **Phase 4** | **Efficiency** | Migrate from DOM extraction to the CDP Accessibility Tree (AxTree); implement Context Compaction. | `manifest.json`, `background.js`, `context.py` |