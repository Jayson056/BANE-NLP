# Bane-FACEBOOK: Personal Proxy Architecture & Strategy

**Lead Engineer:** Jayson Apable Combate
**Project Focus:** Personal Account Integration (DOM-Scraping / UI Automation)

This document outlines the strategy for modifying the BANE-NLP architecture to function as a digital proxy for a personal Facebook account. Because Meta strictly prohibits webhooks or official API access for personal Messenger accounts, this implementation relies on a secondary Chrome Extension acting as a bi-directional DOM scraper and UI automator on `messenger.com`.

---

## 1. System Overview & Architecture

The core philosophy remains intact: utilize a Python `asyncio` backend to orchestrate interactions. However, instead of webhooks, the system introduces a **Dual-Bridge Architecture**:

1.  **The LLM Bridge:** Your existing extension interacting with Gemini/ChatGPT.
2.  **The Messenger Bridge:** A new Chrome Extension running passively on a pinned `messenger.com` tab, monitoring DOM mutations for incoming messages and simulating keyboard events to send replies.

### Modified Technology Stack
* **Backend:** Python 3 (`asyncio`).
* **Intake & Delivery:** Chrome Extension (`content_messenger.js`) using `MutationObserver` and UI automation.
* **WebSockets:** Dual WebSocket servers. One handling the LLM Bridge, the other handling the Messenger Bridge.
* **Database:** SQLite (`bane_data.db`) grouping conversation threads by Messenger Thread ID.

---

## 2. The 7-Layer Pipeline Adaptation

The existing 7-Layer Engine requires specific modifications to handle the volatility of web-scraped data and the sensitive nature of personal inboxes.

* **Layer 1: Intake (`messenger_scraper.py`)**
    * Replaces webhook handling. A dedicated WebSocket server listens for JSON payloads sent by `content_messenger.js` whenever a new message bubble appears on screen.
    * Strips out UI-specific metadata (e.g., "Seen at 9:00 PM") and isolates the sender's name and message text.
* **Layer 2: Context Assembly**
    * Groups contexts strictly by `messenger_thread_id`. Because personal chats have deep histories, it must aggressively utilize the experimental `knowledge_memory` to recall past interactions without overloading the LLM context window.
* **Layer 3 & 4: Composer & Payload Builder**
    * Injects the `JAYSON_PROXY.md` context (detailed in Section 3) instead of the standard BANE-NLP persona.
* **Layer 5: LLM Bridge Executor**
    * Executes exactly as currently implemented, dispatching the prompt to Gemini/ChatGPT via WebSocket.
* **Layer 6: Analyzer (Restricted Autonomous Loop)**
    * **Crucial Security Measure:** The autonomous loop must be heavily restricted for personal chats. While the standard pipeline allows terminal execution (`command_tools`) and file writing, the Messenger Proxy should *only* have access to read-only tools (web search, schedule lookup, logging) to prevent accidental execution of malicious commands sent by friends or strangers.
* **Layer 7: Renderer & Delivery**
    * Instead of making an API call, the Python backend sends a structured JSON payload back to `content_messenger.js`.
    * The extension targets the Messenger text input box, uses the `ClipboardEvent` or simulated keystrokes to inject the text, and triggers a simulated "Enter" keypress.

---

## 3. The "Jayson Proxy" Injection Context

To handle friends, family, and professional inquiries authentically, the standard `BANE_NLP_BRAIN_knowledge.md` must be swapped with a highly specific personal persona.

**`Docs/InjectionHeaderContext/JAYSON_PROXY.md`**

* **Identity Lock:** "You are the digital proxy for Jayson Apable Combate. Speak naturally, casually, and politely. Always make it clear that you are an AI assistant managing his inbox while he is currently busy or away from his desk."
* **Core Knowledge Base:**
    * Jayson is an irregular BSIT student at the Polytechnic University of the Philippines (PUP).
    * He is the lead engineer and developer of the BANE-NLP system.
    * He is currently based in Antipolo, Calabarzon.
* **Behavioral & Tool Directives:**
    * If a message is casual chatter, respond briefly and friendly.
    * If someone asks for a meetup, reference the Antipolo location.
    * If academics are mentioned, relate it to PUP or IT coursework (Python, JavaScript, C, system administration).
    * **Urgent Override:** If the message implies an emergency, an urgent academic requirement, or a critical system outage, do not engage in conversation. Immediately output a JSON tool call to `trigger_sms_alert` (or a similar notification tool) to ping Jayson's physical device.

---

## 4. Technical Challenges & Implementation Solutions

### Challenge 1: Obfuscated DOM on Messenger.com
Meta aggressively changes and obfuscates CSS classes (e.g., `<div class="x1y123...">`).
* **Solution:** Your `content_messenger.js` cannot rely on class names. You must use ARIA roles and relative DOM positioning. For example, look for elements with `role="row"` or `aria-label` matching incoming message patterns to extract text, and `role="textbox"` to locate the reply field.

### Challenge 2: Background Tab Throttling
Chrome severely throttles JavaScript execution and WebSocket connections in inactive background tabs.
* **Solution:** Ensure the Chrome Profile running `messenger.com` has memory saver features disabled for that site. Consider playing a silent audio file in the extension or using Manifest V3's `chrome.alarms` to keep the background service worker alive and the WebSocket connection to Layer 1 open.

### Challenge 3: Group Chat Rate Limiting
If added to a highly active group chat, the scraper will send every single message to the backend, overwhelming the system and rapidly exhausting the LLM's rate limits.
* **Solution:** Implement a strict "Mention Only" rule in Layer 1. The Python `messenger_scraper.py` should immediately drop any payload from a group thread unless the message explicitly contains a trigger word (e.g., "@Jayson" or "Bane"). 

### Challenge 4: Media Handling
* **Solution:** While BANE currently handles image/video generation, extracting incoming images from Messenger via DOM scraping is complex due to Meta's blob URLs. For Phase 1, instruct the `MutationObserver` to simply pass a text placeholder like `[User sent an attachment]` to the LLM.