# BANE-NLP Architecture & System Overview

This document provides a comprehensive breakdown of the BANE-NLP system, detailing its structure, technology stack, components, and operational pipeline.

## 1. System Overview & Tech Stack

**BANE-NLP** (Bane Notebook Pipeline) is an autonomous execution agent that acts as a bridge between messaging platforms (Telegram, Messenger) and web-based LLMs (Google Gemini, Google NotebookLM, OpenAI ChatGPT). It allows users to interact with these AI models via chat while granting the AI the ability to execute code, manipulate files, and perform system-level tasks on the host machine through a Model Context Protocol (MCP) toolset.

### Technology Stack
*   **Backend / Orchestration:** Python 3 (Heavy use of `asyncio` for non-blocking operations).
*   **C-Backend (Proxy/Security):** C (winsock2) for a lightweight webhook server proxy (`bane_server.c`).
*   **WebSockets:** `websockets` library in Python and native WebSockets in JavaScript for bidirectional communication between the Python backend and the Chrome Extension.
*   **Browser Automation/Bridge:** Chrome Extension (Manifest V3) running persistent background service workers and content scripts isolated by Chrome Profiles.
*   **Channels (Bot APIs):** `python-telegram-bot` for Telegram, `aiohttp` web server for Facebook Messenger webhooks.
*   **Database:** SQLite (`bane_data.db`) with WAL mode for fast, concurrent access.
*   **Voice Engine (TTS / STT):** `edge-tts` (Microsoft Edge Text-to-Speech API) for voice generation, and `faster-whisper` for audio transcription.
*   **Process Management:** `subprocess` and Windows commands, FFmpeg for audio processing.

---

## 2. Codebase Structure

The project is modularized into the following key directories:

*   **`core/`**: Central orchestration logic, database handling, security, logging, and the command router.
*   **`channels/`**: Platform-specific adapters (Telegram, Messenger) handling incoming messages and formatting outgoing responses.
*   **`pipeline/`**: The multi-layered processing engine that handles a request from intake to final execution and response.
*   **`chrome_extension/`**: The browser plugin that injects prompts into the web-based LLM UIs and extracts their responses.
*   **`mcp/`**: The Model Context Protocol tool registry containing all the Python scripts the AI can execute locally.
*   **`services/`**: Independent service modules like the `voice_engine` and `email_handler`.
*   **`backend_c/`**: A lightweight C-based server that acts as a front-facing proxy for Messenger webhooks.
*   **`Docs/InjectionHeaderContext/`**: System prompts, personas, and the BANE "Brain" knowledge base injected into the LLM.

---

## 3. The BANE Pipeline (7-Layer Engine)

The core of BANE-NLP is its `PipelineEngine` (`pipeline/engine.py`), which processes requests through a strict sequence:

1.  **Layer 1: Intake (`intake.py`)**
    *   Interprets the raw user message.
    *   Detects inline target overrides (e.g., `@gemini`, `@chatgpt`).
    *   Classifies intent (image generation, video, document, general).
    *   Applies safety guardrails (length limits, empty checks).
2.  **Layer 1.5: TGPT Orchestrator (`tgpt_orchestrator.py`)**
    *   For complex tasks, invokes the `tgpt` CLI to generate a structured, step-by-step Workflow Plan. Simple conversational intents skip this to save time.
3.  **Layer 2: Context Assembly (`context.py`)**
    *   Builds the state bag passed through all stages. Fetches conversation history and dynamic context from the database.
4.  **Layer 3 & 4: Composer (`composer.py`) & Payload Builder**
    *   Assembles the final prompt.
    *   Injects the `BANE_NLP_BRAIN_knowledge.md` persona, available MCP tools, designated save paths, and the active Chrome profile context.
    *   Builds the JSON payload for the WebSocket bridge.
5.  **Layer 5: Bridge Executor (`bridge_executor.py`)**
    *   Checks Chrome profile connectivity.
    *   Acquires an `asyncio.Lock` (`browser_lock`) to ensure serialized execution.
    *   Dispatches the payload via WebSocket to the Chrome Extension.
    *   Waits for and receives the raw response from the LLM.
6.  **Layer 6: Analyzer (`analyzer.py` / Engine Loop)**
    *   Parses the LLM's response.
    *   **The Autonomous Loop:** If the response is a JSON block requesting a tool call (`"call_tool"`), the analyzer intercepts it, executes the corresponding Python tool locally, and loops back to Layer 3, feeding the `[TOOL RESULT]` back to the LLM. This allows multi-step tasks.
7.  **Layer 7: Renderer / Delivery**
    *   Once the LLM outputs a human-readable text response (no more tool calls), the pipeline extracts text, suggestions, and media, generates TTS if requested, and dispatches the bundle back to the respective channel.

---

## 4. Chrome Extension Bridge

Instead of using official API endpoints (which can be costly or restrictive), BANE-NLP uses a custom Chrome Extension (`chrome_extension/`) to puppet web interfaces.

*   **`background.js`**: The service worker that maintains a persistent WebSocket connection (`ws://127.0.0.1:8766`) to `browser_bridge.py`. It manages tab inventory and routes payloads to specific tabs based on target (`gemini`, `chatgpt`, etc.) and `chrome_profile`.
*   **Content Scripts (`content_gemini.js`, etc.)**: Injected into the target web pages. They manipulate the DOM to paste the prompt, simulate button clicks, monitor the UI for completion, and extract the generated response (including images, files, and text).
*   **Profile Isolation**: Supports multiple Chrome Profiles simultaneously. The Python bridge tracks which profile is active for a user and ensures payloads are sent to the correct isolated browser session.

---

## 5. Model Context Protocol (MCP)

The `mcp/` directory defines the AI's physical capabilities.

*   **Registry (`mcp_registry.py`)**: Dynamically scans the `mcp/` folder and registers any function decorated with `@mcp_tool`.
*   **Self-Evolution (Dynamic Tools)**: The AI has a tool (`meta_tools.create_tool`) to write Python code and register it on the fly into `mcp/dynamic/`. The registry `hot_reload()`s to make the tool instantly available without restarting the engine.
*   **Tool Categories**:
    *   `command_tools`: Terminal execution.
    *   `file_tools`: Reading, writing, listing, and creating files (crucially, `write_file_b64` is used for robust script writing).
    *   `desktop_tools`: Screenshots, process management.
    *   `communication_tools`: Telegram messages, emails.
    *   `media_tools`: Format conversion, Base64 encoding.

---

## 6. Channels & Routing

*   **Command Router (`core/command_router.py`)**: Centralizes logic for user commands (`/start`, `/voice`, password entry for gated profiles). It determines the user's active target and profile.
*   **Telegram Bot (`channels/telegram_bot.py`)**: Uses polling. Provides a rich "Heads-Up Display" (HUD) that updates in real-time as the AI executes the autonomous loop, showing status, trace logs, and iterations.
*   **Messenger Bot (`channels/messenger_bot.py`)**: Uses Webhooks. Processes audio via FFmpeg and `faster-whisper` for voice notes. Adapts markdown to Messenger's format limitations.
*   **C-Backend Proxy (`backend_c/bane_server.c`)**: A lightweight C server running on port 8080 that handles Facebook webhook verification and proxies POST requests to the Python engine.

---

## 7. Services & Core Components

*   **Database (`core/database.py`)**: SQLite normalized schema tracking `users`, `conversations`, `messages`, `ai_sessions` (with latency metrics), and an experimental `knowledge_memory`. It enforces profile separation at the conversation level.
*   **Voice Engine (`services/voice_engine.py`)**: Uses `edge-tts` to generate high-quality speech. It includes language detection to automatically switch between English and Tagalog voices based on the text content, and converts MP3 to OPUS/OGG using FFmpeg for Telegram voice note compatibility.
*   **Logger (`core/logger.py`)**: Consolidated logging (`bnp_system.log`) with automatic error forwarding to the admin via Telegram.
*   **Security (`core/security.py`)**: Rate limiting, input sanitization (stripping control chars), and payload validation.

---

## 8. Injection Context & "The Brain"

The AI's behavior is strictly governed by `Docs/InjectionHeaderContext/BANE_NLP_BRAIN_knowledge.md`.

*   **Identity Lock**: Enforces the "BANE NLP" persona, overriding the underlying model's default identity.
*   **Workspace Map**: Provides the AI with a map of the `D:\Project_Workspace` and restricts modifications to the BANE engine itself.
*   **JSON Tool Directive**: Mandates that if an action is required, the AI must output *only* a JSON block representing the tool call, wrapped in Markdown backticks.
*   **Formatting Rules**: Defines how the AI should present data to the user (e.g., using specific emojis, double newlines for mobile readability).

This strict injection header is how a standard web LLM is coerced into acting as an autonomous agentic execution engine.
