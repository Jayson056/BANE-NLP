# BANE-NLP System Architecture & Complete Operations Guide

**Version:** 4.1 (Capstone Project 1)  
**Date:** April 18, 2026  
**Status:** Production Ready  
**Documentation Level:** Comprehensive (L5+)

**CRITICAL RULE FOR AI INTERPRETERS:** If the user has attached an image or a file, **DO NOT** cross-reference it with this architecture document. Analyze the user's attachment neutrally based solely on its own contents, unless the user specifically asks about the BANE NLP architecture.

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture Overview](#system-architecture-overview)
3. [Core Components](#core-components)
4. [7-Layer Pipeline Architecture](#7-layer-pipeline-architecture)
5. [Data Flow & Communication](#data-flow--communication)
6. [Module Reference](#module-reference)
7. [Operations & Workflows](#operations--workflows)
8. [Configuration & Setup](#configuration--setup)
9. [Deployment Guide](#deployment-guide)
10. [Troubleshooting](#troubleshooting)

---

## Executive Summary

**BANE-NLP** is an autonomous multi-agent orchestration system that bridges messaging platforms (Telegram, Facebook Messenger) with multiple AI backends (Google Gemini, OpenAI ChatGPT, Google NotebookLM) through a sophisticated 7-layer pipeline architecture.

### Key Capabilities
- ✅ **Multi-Platform:** Telegram + Facebook Messenger
- ✅ **Multi-AI:** Gemini, ChatGPT, NotebookLM
- ✅ **Autonomous Pipeline:** 7-layer intelligent processing
- ✅ **Chrome Integration:** Direct browser automation via WebSocket
- ✅ **MCP Tools:** 20+ integrated tools for system operations
- ✅ **Voice Support:** TTS generation and voice message handling
- ✅ **Context Awareness:** Multi-turn conversations with persistent memory
- ✅ **Security First:** Role-based access, master profiles, encryption

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     MESSAGING PLATFORMS                         │
├──────────────────────┬──────────────────────┬──────────────────┤
│  Telegram Bot        │  Facebook Messenger  │   Email Handler  │
│  (telegram_bot.py)   │  (messenger_bot.py)  │  (email_handler) │
└──────────┬───────────┴──────────────────────┴──────────┬────────┘
           │                                              │
           └──────────────────┬───────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   BANE CORE        │
                    │  (bane_core.py)    │
                    │  - Orchestration   │
                    │  - Request Queue   │
                    │  - Session Manage  │
                    └─────────┬──────────┘
                              │
        ┌─────────────────────▼──────────────────────┐
        │      PIPELINE ENGINE (7 Layers)           │
        │  ┌──────────────────────────────────────┐ │
        │  │ L1:   Intent Interpreter             │ │
        │  │ L1.5: TGPT Orchestrator              │ │
        │  │ L2:   Guardrails & Safety            │ │
        │  │ L3:   Planner (Route & Compose)      │ │
        │  │ L4:   Executor (Browser Bridge)      │ │
        │  │ L5:   Analyzer (Intelligence)        │ │
        │  │ L6:   Composer (Response Format)     │ │
        │  │ L7:   Dispatcher (Delivery)          │ │
        │  └──────────────────────────────────────┘ │
        └─────────────────────┬──────────────────────┘
                              │
        ┌─────────────────────▼──────────────────────┐
        │  BROWSER BRIDGE (WebSocket)                │
        │  - Chrome Extension Communication          │
        │  - Profile Routing                         │
        │  - Response Capture                        │
        │  - Image Extraction                        │
        └─────────────────────┬──────────────────────┘
                              │
        ┌───────┬─────────────┼──────────────┬──────────┐
        │       │             │              │          │
     ┌──▼──┐ ┌─▼─┐ ┌────────▼─────┐ ┌──────▼────┐ ┌──▼───┐
     │GEMINI│ │GPT│ │ NotebookLM   │ │  Chrome   │ │ MCP  │
     │      │ │   │ │              │ │ Extension │ │Tools │
     └──────┘ └───┘ └──────────────┘ └──────────┘ └──────┘
         ▲       ▲        ▲                           ▲
         └───────┴────────┴───────────────────────────┘
                   AI Service Network
```

---

## Core Components

### 1. **Messaging Layer** (Entry Point)

#### Telegram Bot (`telegram_bot.py`)
```
Purpose: Accept user messages via Telegram
├─ Command Handlers
│  ├─ /start - Initialization
│  ├─ /help - Command documentation
│  ├─ /target - AI target selection
│  ├─ /voice - TTS toggle
│  ├─ /new - New conversation
│  ├─ /status - System status
│  ├─ /gemini - Launch Gemini
│  ├─ /chatgpt - Launch ChatGPT
│  └─ /notebooklm - Launch NotebookLM
├─ Message Processing
│  ├─ Text messages
│  ├─ Voice messages (transcription)
│  ├─ Media attachments (photos, documents)
│  └─ Media groups (multiple files)
├─ Response Delivery
│  ├─ Text with formatting
│  ├─ Voice messages (OGG format)
│  ├─ Images & media
│  └─ Keyboard buttons/suggestions
└─ Session Management
   ├─ User profiles
   ├─ AI target selection
   ├─ Voice mode toggle
   └─ Conversation context
```

#### Facebook Messenger (`messenger_bot.py`)
```
Purpose: Webhook receiver for Messenger events
├─ Event Handlers
│  ├─ Message received
│  ├─ Messaging echoes
│  ├─ Account linking
│  └─ Delivery confirmations
├─ Message Processing
│  ├─ Text extraction
│  ├─ Quick replies
│  ├─ Attachments
│  └─ Media files
└─ Response Delivery
   ├─ Text messages
   ├─ Structured templates
   └─ Media responses
```

### 2. **BANE Core** (`bane_core.py`)

```
Purpose: Central orchestration and process management
├─ Request Processing
│  ├─ User authentication
│  ├─ Intent detection
│  ├─ Profile mapping
│  └─ Request queuing (FIFO)
├─ Pipeline Delegation
│  └─ Route to PipelineEngine
├─ Response Handling
│  ├─ Response collection
│  ├─ Audio generation (TTS)
│  └─ Response formatting
└─ Session Management
   ├─ User database tracking
   ├─ Conversation history
   ├─ Chrome profile management
   └─ Context preservation
```

### 3. **Browser Bridge** (`browser_bridge.py`)

```
Purpose: WebSocket communication hub with Chrome extension
├─ Connection Management
│  ├─ Client registration
│  ├─ Profile-target mapping
│  ├─ Connection pooling
│  └─ Heartbeat monitoring
├─ Message Routing
│  ├─ Request dispatch → Extension
│  ├─ Response collection ← Extension
│  ├─ Profile matching
│  └─ Target resolution
├─ Data Handling
│  ├─ Payload serialization
│  ├─ File encoding (base64)
│  ├─ Image extraction
│  └─ Clipboard interception
└─ Error Handling
   ├─ Timeout detection
   ├─ Connection recovery
   ├─ Fallback strategies
   └─ Graceful degradation
```

---

## 7-Layer Pipeline Architecture

### **Layer 1: Intent Interpreter** (`pipeline/interpreter.py`)

**Purpose:** Analyze user message and classify user intent

```
INPUT:  "Can you write a Python script for network security?"
         ↓
PROCESSING:
├─ Tokenization & NLP
├─ Intent classification
│  ├─ general (default)
│  ├─ code_generation
│  ├─ question_answering
│  ├─ data_analysis
│  ├─ creative
│  ├─ system_command
│  └─ unknown
├─ Entity extraction
│  ├─ Programming language
│  ├─ Domain/topic
│  ├─ Specific requirements
│  └─ Constraints
└─ Confidence scoring
         ↓
OUTPUT: {
  "intent": "code_generation",
  "entities": {"language": "python", "domain": "security"},
  "confidence": 0.95
}
```

### **Layer 1.5: TGPT Orchestrator** (`pipeline/tgpt_orchestrator.py`)

**Purpose:** Generate workflow plan based on intent

```
INPUT:  Intent classification
         ↓
PROCESSING:
├─ Workflow Planning
│  ├─ Task decomposition
│  ├─ Subtask sequencing
│  ├─ Dependency mapping
│  └─ Resource allocation
├─ Target Selection
│  ├─ Model matching (Gemini vs GPT vs NotebookLM)
│  ├─ Capability assessment
│  ├─ Context suitability
│  └─ Profile selection
└─ Instruction Generation
   ├─ Process steps
   ├─ Tool requirements
   ├─ Parameter specification
   └─ Fallback strategies
         ↓
OUTPUT: {
  "workflow": [step1, step2, ...],
  "target": "gemini",
  "profile": "Profile 11",
  "estimated_time": "15s"
}
```

### **Layer 2: Guardrails & Safety** (`pipeline/guardrails.py`)

**Purpose:** Validate request and enforce safety constraints

```
INPUT:  {intent, entities, workflow}
         ↓
CHECKS:
├─ Content Filtering
│  ├─ Malicious content detection
│  ├─ Harmful requests blocked
│  ├─ PII protection
│  └─ Sensitive data masking
├─ Rate Limiting
│  ├─ User quota tracking
│  ├─ API limits enforcement
│  ├─ Token budgeting
│  └─ Throttle enforcement
├─ Authorization
│  ├─ User role validation
│  ├─ Profile permissions
│  ├─ Feature access control
│  └─ Master profile verification
├─ Resource Validation
│  ├─ File size limits
│  ├─ Timeout budgets
│  ├─ Memory constraints
│  └─ Bandwidth checks
└─ Risk Assessment
   ├─ Request complexity scoring
   ├─ Reliability estimation
   ├─ Fallback viability
   └─ Abort conditions
         ↓
OUTPUT: {
  "approved": true,
  "risk_level": "low",
  "reason": "Safe, routine request"
}
```

### **Layer 3: Planner** (`pipeline/planner.py`)

**Purpose:** Compose final prompt and resolve target details

```
INPUT:  Approved request
         ↓
PROCESS:
├─ Context Assembly
│  ├─ User profile info
│  ├─ Conversation history (max 8 turns)
│  ├─ System knowledge base
│  └─ Course/subject context
├─ Prompt Engineering
│  ├─ Injection header generation
│  │  ├─ [MASTER PROFILE] tags
│  │  ├─ [KNOWLEDGE BASE] references
│  │  ├─ [EXECUTION COMMAND] directives
│  │  └─ [SYSTEM NOTICE] instructions
│  ├─ Persona injection (AI skills)
│  ├─ Message formatting
│  └─ File attachment preparation
├─ Payload Building
│  ├─ Serialization
│  ├─ File encoding (base64)
│  ├─ Metadata assembly
│  └─ Timestamp attachment
└─ Profile Confirmation
   ├─ Chrome profile validation
   ├─ Connection verification
   ├─ Fallback profile assignment
   └─ Target-profile mapping
         ↓
OUTPUT: {
  "final_prompt": "Full execution-ready prompt",
  "payload": {...},
  "target": "gemini",
  "profile": "Profile 11",
  "session_id": "bea207bc"
}
```

### **Layer 4: Executor** (`pipeline/executor.py`)

**Purpose:** Send request to browser and capture response

```
INPUT:  {final_prompt, payload, target, profile}
         ↓
EXECUTION:
├─ Browser Queue Management
│  ├─ FIFO queuing (one request at a time)
│  ├─ Lock acquisition
│  ├─ Profile routing decision
│  └─ Connection validation
├─ Payload Dispatch
│  ├─ WebSocket transmission
│  ├─ Extension reception
│  ├─ DOM injection
│  └─ Send button simulation
├─ Response Monitoring
│  ├─ Stability tracking (3+ ticks)
│  ├─ Content completion detection
│  ├─ Streaming aggregation
│  ├─ Timeout management
│  └─ Error recovery
├─ Response Capture
│  ├─ Main copy button attempt
│  ├─ Code block fallback
│  ├─ Full answer extraction (NEW)
│  ├─ Image detection & extraction
│  └─ Metadata collection
└─ Cleanup
   ├─ Socket cleanup
   ├─ Temporary file removal
   └─ Session termination
         ↓
OUTPUT: {
  "raw_response": {...},
  "text": "Full AI answer (explanation + code + context)",
  "images": [],
  "status": "success",
  "timestamp": "2026-04-14T17:08:31"
}
```

### **Layer 5: Analyzer** (`pipeline/analyzer.py`)

**Purpose:** Extract tools/actions from AI response and execute autonomously

```
INPUT:  {raw_response, text}
         ↓
ANALYSIS:
├─ Tool Call Extraction
│  ├─ JSON parsing
│  ├─ Format normalization
│  ├─ Validation & repair
│  └─ Hallucination detection
├─ Tool Execution
│  ├─ MCP tool registry lookup
│  ├─ Argument assembly
│  ├─ Timeout management (60s)
│  ├─ Result collection
│  └─ Error handling
│     ├─ Timeout recovery
│     ├─ Exception capture
│     └─ Fallback execution
├─ Iterative Loop Management
│  ├─ Context-aware feedback
│  ├─ Result injection
│  ├─ Max iterations (5)
│  ├─ Error thresholds
│  └─ Abort conditions
└─ Decision Making
   ├─ Loop termination criteria
   ├─ Final response readiness
   ├─ Incomplete detection
   └─ Graceful exit
         ↓
OUTPUT: {
  "iterations": 1,
  "tools_executed": 0,
  "tool_results": {...},
  "task_complete": true,
  "final_text": "Task complete response"
}
```

### **Layer 6: Composer** (`pipeline/composer.py`)

**Purpose:** Format response for delivery

```
INPUT:  Final AI text
         ↓
PROCESSING:
├─ Text Formatting
│  ├─ Markdown normalization
│  ├─ HTML entity escaping
│  ├─ Code block detection
│  ├─ Special character handling
│  └─ Emoji preservation
├─ Response Structuring
│  ├─ Header addition (platform header)
│  ├─ Footer addition (timestamp + branding)
│  ├─ Section organization
│  └─ Visual hierarchy
├─ Media Processing
│  ├─ Image attachment handling
│  ├─ Voice synthesis (if enabled)
│  │  ├─ Text-to-speech
│  │  ├─ OGG format encoding
│  │  └─ Audio file generation
│  └─ File metadata
├─ Splitting Logic
│  ├─ Character limit check (4000 chars/message)
│  ├─ Message segmentation
│  ├─ Part numbering
│  └─ Continuation markers
└─ Delivery Package
   ├─ Text content
   ├─ Audio data
   ├─ Image references
   ├─ Metadata
   └─ Formatting directives
         ↓
OUTPUT: {
  "text": "Formatted message(s)",
  "audio_path": "audio.ogg | null",
  "images": ["img1.jpg", ...],
  "part_count": 1,
  "requires_split": false
}
```

### **Layer 7: Dispatcher** (`pipeline/dispatcher.py`)

**Purpose:** Deliver response to user via appropriate platform

```
INPUT:  {text, audio, images, metadata}
         ↓
DISPATCH:
├─ Platform Routing
│  ├─ Telegram
│  │  ├─ Text message (reply_text)
│  │  ├─ Voice message (reply_voice)
│  │  ├─ Photo delivery (reply_photo)
│  │  └─ Media upload
│  ├─ Facebook Messenger
│  │  ├─ Text structured message
│  │  ├─ Attachment upload
│  │  ├─ Template rendering
│  │  └─ Quick reply buttons
│  └─ Email
│     ├─ Formatted body
│     ├─ Attachment encoding
│     └─ SMTP transmission
├─ Error Handling
│  ├─ Delivery retry logic
│  ├─ Timeout management
│  ├─ Platform-specific errors
│  └─ Graceful fallback
├─ Confirmation
│  ├─ Delivery acknowledgment
│  ├─ User receipt confirmation
│  └─ Metadata logging
└─ Database Archival
   ├─ Response storage
   ├─ Execution log
   ├─ Performance metrics
   └─ Usage statistics
         ↓
OUTPUT: {
  "delivery_status": "success",
  "message_id": "tg_msg_12345",
  "platform": "telegram",
  "timestamp": "2026-04-14T17:08:33"
}
```

---

## Data Flow & Communication

### **Request Flow (End-to-End)**

```
USER (Telegram)
    ↓ [Message w/ optional attachments]
    ↓
TELEGRAM_BOT
    ├─ Parse message
    ├─ Download attachments
    ├─ Identify AI target (@gemini, @chatgpt, @notebooklm)
    └─ Queue request
    ↓
BANE_CORE
    ├─ User authentication
    ├─ Profile mapping
    ├─ Request validation
    └─ Create session
    ↓
PIPELINE_ENGINE (7 Layers)
    ├─ [L1] Classify intent
    ├─ [L1.5] Generate workflow plan
    ├─ [L2] Validate safety
    ├─ [L3] Compose prompt
    ├─ [L4] Send to browser → Wait for response
    ├─ [L5] Analyze AI response + Execute tools (Loop if needed)
    ├─ [L6] Format for delivery
    └─ [L7] Dispatch to user
    ↓
BROWSER_BRIDGE (WebSocket)
    ├─ Route to Chrome extension (based on profile + target)
    ├─ Extension injects prompt
    ├─ Extension captures response
    └─ Return to pipeline
    ↓
AI_BACKEND (Gemini/ChatGPT/NotebookLM)
    ├─ Process in browser
    ├─ Stream response
    └─ Extension captures full answer
    ↓
USER (Telegram)
    └─ Receives formatted response
```

### **Chrome Extension Communication**

```
EXTENSION ←→ PYTHON BACKEND (WebSocket)

Message Types:
1. Prompt Injection
   Python → Extension:
   {
     "type": "prompt",
     "id": "request_id",
     "payload": {
       "message": "User prompt",
       "files": [{base64 data}],
       "target": "gemini"
     }
   }

2. Response Capture
   Extension → Python:
   {
     "type": "response",
     "id": "request_id",
     "payload": {
       "text": "Full answer extracted",
       "images": ["img1", "img2"],
       "metadata": {...}
     }
   }

3. Status Updates
   Extension → Python (every 50-100ms):
   {
     "type": "status",
     "status": "[L4] Waiting for response...",
     "progress": 0-100
   }

4. Logging
   Extension → Python:
   {
     "type": "log",
     "source": "Gemini",
     "text": "Log message"
   }
```

### **Database Schema**

```
USERS
├─ user_id (Platform ID)
├─ db_user_id (Internal)
├─ platform (telegram/messenger/email)
├─ created_at
└─ metadata

CONVERSATIONS
├─ conversation_id
├─ db_user_id
├─ platform
├─ chrome_profile
├─ created_at
├─ last_interaction
└─ context_summary

MESSAGES
├─ message_id
├─ conversation_id
├─ author (USER/AI)
├─ content
├─ ai_model (gemini/chatgpt/notebooklm)
├─ timestamp
└─ metadata

AI_SESSIONS
├─ session_id
├─ conversation_id
├─ intent
├─ workflow_plan
├─ tools_executed []
├─ duration_ms
├─ status (success/failed/partial)
└─ timestamp
```

---

## Module Reference

### **Core Python Files**

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `bane_core.py` | Central orchestration | `BaneCore`, `process_request()` |
| `browser_bridge.py` | WebSocket server | `BrowserBridge`, `broadcast()` |
| `response_handler.py` | Response parsing | `ResponseHandler`, `extract_text()` |
| `telegram_bot.py` | Telegram integration | `TelegramBot`, `_handle_message()` |
| `messenger_bot.py` | Messenger integration | `MessengerBot`, webhook handlers |
| `database.py` | Database operations | `ensure_user()`, `save_message()` |
| `context_builder.py` | Context assembly | `build_context()` |
| `payload_builder.py` | Request packaging | `build_payload()` |
| `security.py` | Security utilities | `sanitize_input()`, encryption |
| `logger.py` | Logging system | `log_event()`, `log_error()` |
| `voice_engine.py` | TTS generation | `VoiceEngine`, `generate_speech()` |
| `config.py` | Configuration | Constants, credentials, settings |
| `email_handler.py` | Email utilities | Email delivery, parsing |
| `generate_bane_nlp_tts.py` | TTS processing | Voice synthesis utilities |
| `run.py` | Entry point | Application startup |

### **Pipeline Modules**

| File | Layer | Function |
|------|-------|----------|
| `pipeline/interpreter.py` | L1 | Intent classification |
| `pipeline/tgpt_orchestrator.py` | L1.5 | Workflow planning |
| `pipeline/guardrails.py` | L2 | Safety validation |
| `pipeline/planner.py` | L3 | Prompt composition |
| `pipeline/executor.py` | L4 | Browser execution |
| `pipeline/analyzer.py` | L5 | Tool execution & loop |
| `pipeline/composer.py` | L6 | Response formatting |
| `pipeline/dispatcher.py` | L7 | Response delivery |
| `pipeline/engine.py` | Core | Pipeline orchestration |
| `pipeline/context.py` | Core | Context object definition |

### **MCP Tools** (`mcp/`)

| Category | Tools |
|----------|-------|
| **Analysis** | Code analysis, data extraction |
| **Command** | Shell execution, system commands |
| **Communication** | Message sending, notifications |
| **File** | File operations, manipulation |
| **Intelligence** | Knowledge retrieval, reasoning |
| **Media** | Image processing, media handling |
| **Memory** | Context storage, recall |
| **Meta** | System introspection, metadata |
| **Network** | HTTP requests, API calls |
| **System** | OS operations, environment |
| **Utility** | General helpers, parsing |
| **Voice** | Audio processing, TTS |
| **Web** | Web scraping, HTML parsing |

### **Chrome Extension** (`chrome_extension/`)

| File | Purpose |
|------|---------|
| `manifest.json` | Extension configuration |
| `background.js` | Extension background service |
| `content_gemini.js` | Gemini.com interaction |
| `content_chatgpt.js` | ChatGPT interaction |
| `content_notebooklm.js` | NotebookLM interaction |
| `websocket_bridge.js` | WebSocket communication |

---

## Operations & Workflows

### **Workflow 1: Standard Question Answering**

```
User: "What is Python?"

Pipeline:
L1 → Intent: question_answering
L1.5 → Target: gemini (default)
L2 → Safety: approved
L3 → Prompt: Inject with BANE knowledge base
L4 → Execute: Send to Gemini in Chrome
L5 → Analyze: No tools needed (single response)
L6 → Compose: Format with explanation + code
L7 → Dispatch: Send to Telegram

Result: Full explanation sent to user (not just code!)
```

### **Workflow 2: Code Generation with Files**

```
User: "Analyze this file and generate a fix" (+ file attachment)

Pipeline:
L1 → Intent: code_analysis
L1.5 → Target: chatgpt (better for code)
L2 → Safety: Scan file for malware, check size
L3 → Prompt: Encode file in base64, attach to payload
L4 → Execute: Send file + prompt to ChatGPT
L5 → Analyze: Extract code suggestions, execute tests if possible
L6 → Compose: Format code with explanations
L7 → Dispatch: Split if >4000 chars, send to Telegram

Result: Analysis + fixed code delivered
```

### **Workflow 3: Multi-Agent Tool Execution**

```
User: "Create a scheduled task and verify it's running"

Pipeline:
L1 → Intent: system_operation
L1.5 → Target: gemini (with MCP tools enabled)
L2 → Safety: Verify permissions (master profile)
L3 → Prompt: Include tool registry
L4 → Execute: Send to Gemini
L5 → Analyze:
     - Extract: {"call_tool": "schedule_task", "args": {...}}
     - Execute: Registry runs task
     - Feedback: "Success: Task scheduled"
     - Generate: New prompt with results
     - Loop back to L4 if more tools needed
L6 → Compose: Format execution report
L7 → Dispatch: Send status to user

Result: Task executed autonomously with user notification
```

### **Workflow 4: Voice Message Processing**

```
User: Sends voice message to Telegram

Pipeline:
1. Telegram Bot receives OGG voice
2. Transcribe voice → text (speech-to-text)
3. Process as normal text message through pipeline
4. AI generates response
5. If voice_mode=ON:
   - Composer generates TTS
   - Create OGG audio file
   - Dispatcher sends both text + voice
6. User receives formatted text + audio response

Result: Voice-in, voice-out interaction
```

### **Workflow 5: Master Profile Authorization**

```
User: Attempts /gemini (Profile 4 - Capstone Project)

Authentication:
1. Telegram bot: "Select profile type"
2. User: Clicks "Profile 4 - Capstone"
3. Bot: "Enter access password"
4. User: Sends password
5. Bot: Validates against PROFILE_PASSWORD
6. If correct:
   - Pre-register profile in browser bridge
   - Launch Chrome with Profile 4
   - Connect WebSocket
   - All AI requests route through Profile 4
   - Full MCP tool access granted
7. If wrong: Access denied

Security:
- Time-limited verification window (90s)
- One password attempt per session
- Logging of all access attempts
- Session tied to user ID
```

---

## Configuration & Setup

### **Environment Variables** (`config.yml`)

```yaml
# Database
DATABASE_URL: "sqlite:///bane.db"

# Messaging APIs
TELEGRAM_TOKEN: "your_token"
TELEGRAM_WEBHOOK: "https://your-server.com/telegram"
MESSENGER_VERIFY_TOKEN: "your_token"
MESSENGER_PAGE_ACCESS_TOKEN: "your_token"

# Browser Communication
WEBSOCKET_HOST: "127.0.0.1"
WEBSOCKET_PORT: 8766

# Chrome Profiles Configuration
CHROME_PROFILES:
  "Profile 4":
    label: "Capstone Project 1"
    url: "chrome://newtab"
  "Profile 11":
    label: "Information Assurance & Security 1"
    url: "chrome://newtab"

# AI Model Settings
RESPONSE_TIMEOUT: 300  # seconds
MAX_RETRIES: 3
FALLBACK_TARGET: "chatgpt"

# Security
PROFILE_PASSWORD: "your_password"
ENCRYPTION_KEY: "your_key"

# MCP Tools
MCP_TOOLS_ENABLED: true
MCP_TOOL_TIMEOUT: 60  # seconds
MCP_MAX_ITERATIONS: 5
```

### **Python Dependencies** (`requirements.txt`)

```
python-telegram-bot==20.2
flask==2.3.0
websockets==11.0
aiohttp==3.8.0
pydantic==2.0.0
sqlalchemy==2.0.0
beautifulsoup4==4.12.0
requests==2.31.0
pillow==10.0.0
pyttsx3==2.90
librosa==0.10.0
numpy==1.24.0
```

### **Startup Commands**

```bash
# Install dependencies
pip install -r requirements.txt

# Run BANE system
python run.py

# With specific profile
python run.py --profile "Profile 4"

# With logging
python run.py --log-level DEBUG
```

---

## Deployment Guide

### **Local Development**

```bash
# 1. Clone repository
git clone <repo>
cd Bane_NLP

# 2. Create virtual environment
python -m venv banenv
source banenv/bin/activate  # On Windows: banenv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp config.example.yml config.yml
# Edit config.yml with your credentials

# 5. Setup database
python -c "from database import create_tables; create_tables()"

# 6. Start system
python run.py

# 7. In another terminal, load Chrome extension
# Open Chrome → chrome://extensions → Load unpacked → select chrome_extension/
```

### **Production Deployment**

```bash
# 1. Use systemd service
sudo cp bane.service /etc/systemd/system/
sudo systemctl enable bane
sudo systemctl start bane

# 2. Use process manager (PM2)
npm install -g pm2
pm2 start "python run.py" --name "bane-nlp"
pm2 save
pm2 startup

# 3. Setup reverse proxy (Nginx)
# Configure webhook URLs to point to your server
# Use SSL certificates for secure communication

# 4. Monitoring
pm2 monit
tail -f logs/bane.log
```

### **Chrome Extension Setup**

```bash
# 1. Open Chrome
# 2. Go to: chrome://extensions/
# 3. Enable "Developer mode" (top right)
# 4. Click "Load unpacked"
# 5. Select: Bane_NLP/chrome_extension/
# 6. Extension appears with ID: abcdef123456...
# 7. Configure in config.py: EXTENSION_ID = "abcdef123456..."
```

---

## Troubleshooting

### **Issue: Chrome Extension Not Connecting**

```
Diagnosis:
- Check WebSocket server running: netstat -an | grep 8766
- Verify extension loaded: chrome://extensions
- Check browser console for errors: F12 → Console

Solution:
1. Stop BANE: Ctrl+C
2. Ensure port 8766 is free: netstat -ano | grep 8766
3. Restart: python run.py
4. Reload extension: chrome://extensions → Reload
```

### **Issue: AI Model Not Responding (Timeout)**

```
Diagnosis:
- Check Chrome window is active
- Verify Gemini/ChatGPT page is loaded
- Check browser network: F12 → Network

Solution:
1. Extension logs: F12 → Console (in extension context)
2. Python logs: tail -f Terminal_logs.txt
3. Increase RESPONSE_TIMEOUT in config.yml (300s → 600s)
4. Restart browser: Close all Chrome windows, reopen
```

### **Issue: Messages Not Delivered to Telegram**

```
Diagnosis:
- Check Telegram token is valid
- Verify user ID is correct
- Check network connectivity

Solution:
1. Test token: curl -X GET "https://api.telegram.org/botTOKEN/getMe"
2. Check logs: grep "TELEGRAM" Terminal_logs.txt
3. Verify user ID: /info command in Telegram bot
4. Restart Telegram bot: Ctrl+C → python run.py
```

### **Issue: Database Locked**

```
Diagnosis:
- Multiple processes accessing database
- Corrupted SQLite file

Solution:
1. Stop BANE: Ctrl+C
2. Backup database: cp bane.db bane.db.backup
3. Restart: python run.py
4. If persists: Delete bane.db (will recreate schema)
```

### **Issue: High Memory Usage**

```
Diagnosis:
- Memory leak in context building
- Too many images cached
- Long history retention

Solution:
1. Reduce conversation history: MAX_HISTORY = 8 → 4 in context_builder.py
2. Clear old logs: rm logs/*.txt
3. Clear image cache: rm generated_images/*
4. Monitor: watch -n 1 'ps aux | grep run.py'
```

---

## Performance Optimization

### **Caching Strategy**

```
L1.5 Workflow Plans (5 min cache)
├─ Intent → Workflow mapping
├─ Reduces redundant planning
└─ Invalidated on model update

L3 Context Building (Dynamic)
├─ Conversation history (last 8 messages)
├─ User profile (persistent)
├─ Course context (per-session)
└─ Knowledge base (reference only)

L5 Tool Results (Session cache)
├─ Prevents redundant tool execution
├─ Clears on new conversation
└─ Improves iteration performance
```

### **Concurrency Limits**

```
Browser Communication: 1 request at a time (FIFO queue)
└─ Ensures Chrome compatibility, prevents state conflicts

Telegram Bot: Multiple parallel requests (async)
├─ 10+ concurrent users supported
└─ Independent message processing

MCP Tools: 20 concurrent executions
├─ Tool registry manages queueing
└─ 60s timeout per tool

Database: SQLAlchemy connection pool
├─ 10 concurrent connections
└─ Automatic retry on lock
```

---

## Security Model

### **Authentication Layers**

```
Layer 1: Platform Verification
├─ Telegram: Bot token validation
├─ Messenger: Webhook token verification
└─ Email: SMTP authentication

Layer 2: User Authorization
├─ User in allowed list
├─ Rate limits enforced
└─ Feature access control

Layer 3: Master Profile Access
├─ Password verification (90s window)
├─ One-time challenge per session
├─ Audit logging of all access

Layer 4: Data Protection
├─ User inputs sanitized
├─ PII detection + masking
├─ Encrypted storage of sensitive data
└─ TLS for network communication
```

### **Rate Limiting**

```
Per User:
├─ 100 requests per hour
├─ 10 concurrent requests
└─ 50MB files per day

Per AI Backend:
├─ Gemini: 100 req/day (free tier)
├─ ChatGPT: As per API plan
└─ NotebookLM: 50 req/day

Global:
├─ 1000 requests per minute (all users)
└─ 10GB data transfer per day
```

---

## System Monitoring

### **Key Metrics to Track**

```
Performance:
├─ Response time: [L1:X ms] [L2:X ms] [L4:X ms avg]
├─ Throughput: N requests/hour
├─ Concurrency: N active users
└─ Error rate: X% failures

Resource Usage:
├─ CPU: Monitor for spikes
├─ Memory: Track for leaks
├─ Network: I/O operations
└─ Database: Query performance

Quality:
├─ LLM response satisfaction
├─ Tool execution success rate
├─ User engagement
└─ System uptime
```

### **Logging Levels**

```
DEBUG:   Detailed execution flow, all intermediate values
INFO:    Major milestones, user actions, system events
WARNING: Non-critical issues, degradation, slow operations
ERROR:   Failed operations, exceptions, recoverable failures
CRITICAL: System-level failures, unrecoverable errors
```

---

## Future Enhancements (Roadmap)

```
v4.0 (Current)
├─ 7-layer pipeline
├─ 3 AI backends
├─ 2 messaging platforms
└─ MCP tool integration

v4.1 (Planned)
├─ Image generation via DALL-E
├─ Document analysis (PDFs)
├─ Real-time streaming responses
└─ Advanced context summarization

v5.0 (Future)
├─ Multi-user collaboration
├─ Custom model fine-tuning
├─ Advanced analytics dashboard
├─ Mobile app integration
└─ Plugin marketplace
```

---

## Contact & Support

- **Creator:** Jayson Combate (@Jaysoncom)
- **Course:** Capstone Project 1 (Lab & Lecture)
- **Schedule:** Thu 1:30-4:30pm (Lab) | Thu 4:30-6:30pm (Lecture)
- **Knowledge Base:** BANE_CONTEXT_FILES/BANE_NLP_BRAIN_knowledge.md

---

**Last Updated:** April 14, 2026  
**Status:** Production Ready (v4.0)  
**Maintenance:** Active Development
