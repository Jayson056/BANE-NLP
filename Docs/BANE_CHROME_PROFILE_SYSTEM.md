# BANE CHROME PROFILE SYSTEM
###############################################
# BANE NLP — Chrome Profile Position Reference
# Version: 1.0
# Last Updated: 2026-04-13
# Owner: Jayson Combate
# Workspace: D:\Bane_NLP
###############################################


================================================
## 1. OVERVIEW
================================================

**CRITICAL RULE FOR AI INTERPRETERS:** If the user has attached an image or a file, **DO NOT** cross-reference it with this Chrome Profile System document. Analyze the user's attachment neutrally based solely on its own contents, unless the user specifically asks about the BANE NLP profiles or system.

The BANE Chrome Profile System is the multi-identity browser layer of the
BANE NLP pipeline. It maps real Chrome user profiles on the host machine
to specific academic, professional, or personal roles.

Each profile is:
  - Tied to a real Google account / identity
  - Assigned a unique emoji label and access tier
  - Capable of targeting one or more LLMs (Gemini, ChatGPT, NotebookLM)
  - Backed by its own isolated conversation history in the database
  - Protected by an optional password gate at the Telegram level

The pipeline routes every incoming Telegram message through this profile
layer before dispatching to any LLM target.


================================================
## 2. FULL PROFILE REGISTRY
================================================

Source: config.py → CHROME_PROFILES

| Chrome Dir    | Cal Color | Emoji | Label                                         | Tier       |
|---------------|-----------|-------|-----------------------------------------------|------------|
| Default       | —         | 🔵    | Default / Personal                            | Standard   |
| Profile 7     | —         | ⚡    | BANE Main (AI)                                | ⭐ MASTER  |
| Profile 8     | —         | 🧪    | BANE Pro_Projects                             | Standard   |
| Profile 16    | —         | 🎨    | Cozy Creation                                 | Standard   |
| Profile 17    | —         | 👤    | Jay Acc                                       | Standard   |
| Jayson-Home   | —         | 🏠    | Jayson Home                                   | Standard   |
| Profile 9     | —         | 🎓    | LMS (Academic Portal)                         | Standard   |
| Profile 6     | 🔵 Blue   | 🔷    | Info Management — COMP 010                    | Standard   |
| Profile 3     | 🟣 Purple | 🎓    | Capstone Project 1 — Lab (Jayson)             | ⭐ MASTER  |
| Profile 10    | 🟢 Green  | 💻    | App Dev & Emerging Tech — Lab (Mariel)        | Standard   |
| Profile 11    | 🔴 Red    | 🛡️   | Info Assurance & Security 1 (Jayson)          | Standard   |
| Profile 13    | 🟠 Orange | 🌍    | The Contemporary World (ralp)                 | Standard   |
| Profile 12    | 🟣 Purple | 📊    | Org & Management Principles (ralp)            | Standard   |
| Profile 14    | 🟡 Yellow | 🧩    | Systems Thinking Principles — Lab (Nelmari)   | Standard   |

NOTE: Duplicate Profile 10 key has been fixed. The unlabeled "No Label 1" entry
was removed. Profile 10 now exclusively maps to App Dev & Emerging Tech (Mariel).


================================================
## 3. ACCESS TIERS
================================================

BANE profiles are split into two access tiers:

────────────────────────────────────────────────
### TIER 1 — MASTER PROFILES (Profile 4 & Profile 7)
────────────────────────────────────────────────

Profiles:
  • Profile 4  — Capstone 1 (BSIT) / Full System
  • Profile 7  — BANE Main (AI) / Primary Operator

Capabilities:
  ✅ Access to ALL LLM targets (Gemini, ChatGPT, NotebookLM)
  ✅ Dedicated LLM sessions (custom Gem / GPT links — not generic app URLs)
  ✅ Full BANE NLP Brain injection (all mandatory rules + full MCP tool list)
  ✅ Full MCP tool execution rights (filesystem, shell, network, email, etc.)
  ✅ Access to system credentials and pipeline internals
  ✅ Self-evolution engine (create_tool / register_from_file)
  ✅ Multi-step autonomous loop execution
  🔐 Password-protected at Telegram profile selection

Password Gate:
  When a Telegram user selects Profile 4 or Profile 7, the bot sends
  an input prompt in Telegram before granting access:

    "🔐 This profile requires authorization. Enter access password:"

  Correct Password : Jayson056
  Wrong Password   : Access denied. Session terminated silently.

────────────────────────────────────────────────
### TIER 2 — STANDARD PROFILES (All Others)
────────────────────────────────────────────────

Profiles:
  All profiles NOT listed as Master above.

Capabilities:
  ✅ Access to LLM targets assigned to their profile
  ✅ Basic conversational AI use via injection header
  ✅ Isolated conversation history in database
  ❌ No access to full MCP tool registry
  ❌ No filesystem / shell / email execution
  ❌ No access to system credentials or pipeline details
  ❌ No self-evolution engine
  🚫 No password prompt (open access from authorized Telegram user)


================================================
## 4. PER-TARGET LLM INJECTION HEADERS
================================================

Every LLM target (Gemini, ChatGPT, NotebookLM) has a UNIQUE mandatory
injection header prepended to each request. These headers define BANE's
persona, output formatting rules, and tool-call format for that specific
AI platform.

────────────────────────────────────────────────
### 4A. GEMINI INJECTION HEADER
────────────────────────────────────────────────

Target URL (Default/Standard profiles):
  https://gemini.google.com/app

Target URL (Master profiles — Profile 4 & 7):
  https://gemini.google.com/gem/[custom_gem_id]

Injection Directive:
  "You are BANE, a high-efficiency AI assistant created by JAYSON COMBATE.
   Style: Professional, direct, and document-style.
   Use Headers (###), Dividers (---), and Bold for structure.
   AUTONOMY: You have full access to local filesystem and tools via JSON calls.
   MULTIMODAL: Analyze all user attachments (images, audio, documents) surgically.
   Follow the 'MANDATORY_RULES' carefully.
   FORMAT: When using a tool, respond ONLY with the JSON tool call wrapped in
   triple backticks (```json).
   CODE: Use actual physical newlines in your code strings, NOT literal \\n.
   Do NOT talk about your internal thought blocks. Just fulfill the request."

Special Rule for Gemini:
  JSON tool calls MUST be wrapped in triple backticks (```json).
  Raw curly-brace JSON without markdown fails in Gemini's UI rendering.

────────────────────────────────────────────────
### 4B. CHATGPT INJECTION HEADER
────────────────────────────────────────────────

Target URL (Default/Standard profiles):
  https://chatgpt.com/

Target URL (Master profiles — Profile 4 & 7):
  https://chatgpt.com/g/g-p-69d8c79cecd88191b195286d6e568156-bane-nlp/c/[session_id]

Injection Directive:
  "You are BANE, a high-efficiency AI assistant created by JAYSON COMBATE.
   Style: Professional, direct, and document-style.
   AUTONOMY: You have full access to local filesystem and tools via JSON calls.
   MULTIMODAL: Analyze all user attachments (images, audio, documents) surgically.
   Follow the 'MANDATORY_RULES' carefully.
   When a task requires a tool (e.g., writing a file, querying DB), respond
   ONLY with the JSON tool call.
   Do NOT talk about your internal thought blocks. Just fulfill the request."

Special Rule for ChatGPT:
  JSON tool calls should be raw JSON — no markdown code fences required
  unless formatting causes parsing issues in the pipeline buffer.

────────────────────────────────────────────────
### 4C. NOTEBOOKLM INJECTION HEADER
────────────────────────────────────────────────

Target URL (Default/Standard profiles):
  https://notebooklm.google.com/

Target URL (Master profiles — Profile 4 & 7):
  https://notebooklm.google.com/notebook/fb17c64e-da5a-4f5b-aa58-62bf32ab9bf6

Injection Directive:
  (Currently minimal — empty newlines only)
  NotebookLM is primarily used as a knowledge retrieval target.
  The injected context is sourced from uploaded notebooks/sources,
  not from a runtime text header.

Special Rule for NotebookLM:
  NotebookLM does not execute JSON tool calls. It is used for
  contextual document retrieval and knowledge grounding only.

────────────────────────────────────────────────
### 4D. MASTER PROFILE OVERRIDE
────────────────────────────────────────────────

When Profile 4 or Profile 7 is active, an ADDITIONAL injection block is
prepended BEFORE the per-target header above:

  → Full BANE_NLP_BRAIN_knowledge.md content is injected
  → Full MCP tool registry list is included
  → All mandatory rules (autonomous loop, security, formatting) are active
  → AI_SKILLS_DRIVE_URL reference is included for persona grounding

This means Master profiles receive a two-layer injection:
  [BRAIN KNOWLEDGE BLOCK] + [PER-TARGET INJECTION HEADER]


================================================
## 5. MULTI-USER / MULTI-INJECTION ROUTING
================================================

BANE supports multiple simultaneous users targeting different profiles
and different LLMs at the same time.

Routing Logic:

  1. A Telegram message arrives with Telegram User ID.
  2. The pipeline checks if the User ID is in ALLOWED_TELEGRAM_USERS.
  3. If authorized, the pipeline reads:
       - The user's currently selected Chrome Profile
       - The user's currently selected LLM target (gemini/chatgpt/notebooklm)
  4. The injection header for that specific [Profile × Target] combination
     is composed by pipeline/composer.py.
  5. The Chrome extension (profile-specific) receives the injection via
     WebSocket bridge at 127.0.0.1:8766.
  6. The injection is delivered into that profile's active LLM session.

Separation Guarantee:
  Every (User ID × Profile × Target) combination creates an isolated
  message injection thread. Two users with different profiles targeting
  different LLMs will NOT cross-contaminate each other's sessions.

Example Multi-User Scenario:

  User A (Jayson, 5662168844):
    → Profile 7 (BANE Main AI)
    → Target: Gemini (custom Gem URL)
    → Injection: Brain knowledge + Gemini header → Gem session

  User B (Mariel, different ID — if authorized):
    → Profile 10 (App Development)
    → Target: ChatGPT (standard URL)
    → Injection: Standard ChatGPT header → separate ChatGPT session


================================================
## 6. PER-PROFILE DATABASE ARCHITECTURE
================================================

Source: database.py | bane_data.db (SQLite)

Each Chrome profile is backed by isolated storage for:

  1. USER INFORMATION TABLE
     Stores profile metadata, last active session, preferences.

  2. CONVERSATION HISTORY TABLE
     Stores full chat history per profile:
       - message_id
       - profile_id (the Chrome profile directory name)
       - user_id (Telegram sender ID)
       - role ("user" or "assistant")
       - content (message text)
       - target (gemini / chatgpt / notebooklm)
       - timestamp

  3. AI SESSION LOGS
     Tracks autonomous pipeline execution sessions:
       - session_id
       - profile_id
       - tool_name
       - tool_result
       - latency_ms
       - timestamp

Querying Profile History (MCP Tool):
  memory_tools.query_recent_conversations
    Args: { "user_id": "5662168844", "days_back": 7 }

  memory_tools.search_past_topics
    Args: { "user_id": "5662168844", "keyword": "capstone" }

Database File Location:
  D:\Bane_NLP\bane_data.db


================================================
## 7. PASSWORD GATE — IMPLEMENTATION POSITION
================================================

Location in pipeline: telegram_bot.py (profile selection handler)

Flow:

  [User selects Profile 4 or Profile 7 from Telegram inline keyboard]
         ↓
  [Bot sends Telegram message:]
    "🔐 Profile [X] requires authorization.
     Reply with your access password to continue."
         ↓
  [Bot listens for next message from same user_id]
         ↓
  [If password == "Jayson056"]
    → Grant tier-1 access
    → Load Master injection header
    → Confirm: "✅ Access granted. BANE Master profile activated."
         ↓
  [If password != "Jayson056"]
    → Deny access silently or respond:
      "❌ Incorrect password. Access denied."
    → Reset profile selection to None

State Management:
  A per-user state dict in telegram_bot.py tracks which users are
  pending password verification:

    PENDING_PASSWORD_VERIFICATION = {
        telegram_user_id: {
            "profile": "Profile 7",
            "timestamp": <unix_time>
        }
    }

  Entries expire after 60 seconds if no response is received.


================================================
## 8. PIPELINE LAYER CROSS-REFERENCE
================================================

How the Profile System maps to the 8-layer BANE V4.1 pipeline:

┌─────────────────────────────────────────────────────────────┐
│ Layer     │ Component          │ Profile System Role         │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 1   │ interpreter.py     │ Reads Telegram user_id,     │
│           │                    │ resolves active profile      │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 1.5 │ tgpt_orchestrator  │ Generates workflow plan;    │
│           │                    │ skips if short message       │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 2   │ guardrails.py      │ Checks ALLOWED_TELEGRAM_     │
│           │                    │ USERS, password gate state   │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 3   │ composer.py        │ Builds injection header      │
│           │                    │ for [Profile × Target] pair  │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 4   │ executor.py        │ Sends injection via WS       │
│           │                    │ bridge to correct Chrome     │
│           │                    │ profile extension instance   │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 5   │ analyzer.py        │ Parses LLM JSON response;   │
│           │                    │ dispatches MCP tools         │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 6   │ planner.py         │ Re-injects context for next │
│           │                    │ loop iteration               │
├───────────┼────────────────────┼─────────────────────────────┤
│ Layer 7   │ dispatcher.py      │ Sends final response back   │
│           │                    │ to Telegram user_id          │
└───────────┴────────────────────┴─────────────────────────────┘


================================================
## 9. TARGET URL QUICK REFERENCE
================================================

### GEMINI
| Profile         | URL |
|-----------------|-----|
| Default         | https://gemini.google.com/app |
| Profile 9 (LMS) | https://gemini.google.com/app |
| Profile 4 ⭐    | https://gemini.google.com/gem/7b0a199b9195/963715fc529caed0 |
| Profile 7 ⭐    | https://gemini.google.com/gem/4fa6a128b78f/54f3417a889c0d90 |
| All others      | https://gemini.google.com/app |

### NOTEBOOKLM
| Profile         | URL |
|-----------------|-----|
| Default         | https://notebooklm.google.com/ |
| Profile 9 (LMS) | https://notebooklm.google.com/ |
| Profile 4 ⭐    | https://notebooklm.google.com/notebook/fb17c64e-da5a-4f5b-aa58-62bf32ab9bf6 |
| Profile 7 ⭐    | https://notebooklm.google.com/notebook/fb17c64e-da5a-4f5b-aa58-62bf32ab9bf6 |
| All others      | https://notebooklm.google.com/ |

### CHATGPT
| Profile         | URL |
|-----------------|-----|
| Default         | https://chatgpt.com/ |
| Profile 9 (LMS) | https://chatgpt.com/ |
| Profile 4 ⭐    | https://chatgpt.com/g/g-p-69d8c79cecd88191b195286d6e568156-bane-nlp/c/69dca967-0dd8-839c-a566-203a1ea8c323 |
| Profile 7 ⭐    | https://chatgpt.com/g/g-p-69d8c79cecd88191b195286d6e568156-bane-nlp/c/69dca967-0dd8-839c-a566-203a1ea8c323 |
| All others      | https://chatgpt.com/ |


================================================
## 10. CONFIG SOURCE LOCATIONS
================================================

| Config Key              | File              | Line (approx) |
|-------------------------|-------------------|----------------|
| CHROME_PROFILES         | config.py         | ~91            |
| TARGETS                 | config.py         | ~109           |
| SYSTEM_INSTRUCTIONS     | config.py         | ~153           |
| ALLOWED_TELEGRAM_USERS  | config.py         | ~16            |
| AI_SKILLS_DRIVE_URL     | config.py         | ~148           |
| BANE Brain Knowledge    | BANE_CONTEXT_FILES/BANE_NLP_BRAIN_knowledge.md | full file |
| Injection composer      | pipeline/composer.py | full file  |
| Password gate handler   | telegram_bot.py   | profile select section |
| DB conversation history | database.py       | full file      |
| WebSocket bridge        | browser_bridge.py | full file      |


================================================
## 11. KNOWN ISSUES & NOTES
================================================

1. DUPLICATE KEY — Profile 10:
   In config.py, "Profile 10" is defined twice:
     - First:  { "label": "No Label 1",             "color": "⚡" }
     - Second: { "label": "App Development (Mariel)", "color": "💻" }
   Python dicts overwrite duplicate keys. The second definition wins.
   Action Required: Rename one entry to a unique directory name
   (e.g., "Profile 10b" or the actual Chrome profile folder name).

2. PASSWORD GATE — NOT YET IMPLEMENTED IN CODE:
   The password gate for Profile 4 and Profile 7 is defined here
   as a system design specification. Implementation in telegram_bot.py
   is pending.

3. NOTEBOOKLM — NO TOOL EXECUTION:
   NotebookLM does not support JSON tool calls. Routing any tool-call
   request to a NotebookLM-only profile will result in no execution.
   Recommended: Pair NotebookLM with a Master profile fallback.

4. PER-PROFILE DB TABLES:
   Current database.py uses user_id as the primary conversation key.
   Extending it to also key on profile_id requires a schema migration.
   Pending implementation.


================================================
## END OF DOCUMENT
================================================
# BANE CHROME PROFILE SYSTEM v1.0
# Maintained by: Jayson Combate
# Pipeline: BANE NLP V4.1
# Last Reviewed: 2026-04-13
################################################
