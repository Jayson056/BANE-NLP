/**
 * BNP Content Script — NotebookLM
 * =================================
 * Handles prompt injection and response capture on notebooklm.google.com.
 *
 * Strategy:
 *   1. Listen for "bnp-prompt" events from the WebSocket bridge
 *   2. Find NotebookLM's chat input area and inject the prompt text
 *   3. Trigger the send action
 *   4. Observe the DOM for the AI response
 *   5. Dispatch a "bnp-response" event with the response text
 */

(function () {
  "use strict";

  const PIPELINE_NAME = "BNP";
  const POLL_INTERVAL_MS = 500;
  const RESPONSE_TIMEOUT_MS = 60000; // 60 seconds fail-fast limit

  let currentRequestId = null;
  let capturedClipboardText = null;

  const logMsg = (text) => {
    console.log(`[${PIPELINE_NAME} NotebookLM] ${text}`);
    chrome.runtime.sendMessage({
      type: "BNP_BRIDGE_LOG",
      target: "notebooklm",
      payload: text
    });
  };

  // ─── Notify Background ──────────────────────────────────────
  chrome.runtime.sendMessage({
    type: "BNP_CONTENT_READY",
    target: "notebooklm",
  });

  console.log("[BNP NotebookLM] Content script loaded");

  // ─── Request De-duplication ────────────────────────────────
  const processedRequestIds = new Set();

  // ─── Listen for Prompts ─────────────────────────────────────
  window.addEventListener("bnp-prompt", async (event) => {
    const data = event.detail;
    if (!data.id) return;

    // 1. Initial Receipt Log
    console.log(`[BNP NotebookLM] EVENT: bnp-prompt received. ID: ${data.id}, Target: ${data.target}`);

    // De-duplicate: If we've already queued or processed this exact ID, ignore it.
    if (processedRequestIds.has(data.id)) {
      console.warn(`[BNP NotebookLM] Ignoring duplicate prompt ID: ${data.id}`);
      return;
    }
    processedRequestIds.add(data.id);

    // Manage set size (LRU-ish)
    if (processedRequestIds.size > 100) { // Increased history
      const first = processedRequestIds.values().next().value;
      processedRequestIds.delete(first);
    }

    if (data.target !== "notebooklm") {
      console.log("[BNP NotebookLM] Ignoring prompt for different target:", data.target);
      return;
    }

    const message = data.payload?.message;
    if (!message) {
      console.error("[BNP NotebookLM] No message in payload");
      return;
    }

    currentRequestId = data.id;
    capturedClipboardText = null;
    console.log(`[BNP NotebookLM] Processing prompt (${currentRequestId}):`, message.substring(0, 80));

    try {
      // --- MULTI-FILE INJECTION ---
      const files = data.payload?.files || (data.payload?.file ? [data.payload.file] : []);

      if (files.length > 0) {
        // Calculate total upload wait based on all files
        let totalUploadWait = 1500; // SPEED: was 2500ms
        for (const file of files) {
          const base64Length = file.data.length;
          totalUploadWait += Math.min(Math.ceil(base64Length / 500000) * 1000, 20000); // 1s per 500KB, max 20s per file
        }

        console.log(`[BNP NotebookLM] Injecting ${files.length} file(s). Syncing design for ${totalUploadWait}ms...`);

        for (const file of files) {
          console.log(`[BNP NotebookLM] Injecting file: ${file.name}...`);
          await injectFile(file);
          // Small delay between multiple files to allow UI to register
          await delay(500); // SPEED: was 1000ms
        }
        await delay(totalUploadWait); // Wait for all files to be processed by NotebookLM UI

        // Logical Sync: Wait for send button to become active
        for (let i = 0; i < 10; i++) {
          const btn = document.querySelector('button[aria-label*="Send"], button[aria-label*="send"]');
          if (btn && !btn.disabled) break;
          await delay(1000);
        }
      }
      await injectPrompt(message);
    } catch (err) {
      console.error("[BNP NotebookLM] Injection failed:", err);
      sendErrorResponse(currentRequestId, `Injection failed: ${err.message}`);
    }
  });

  // ─── File Injection ─────────────────────────────────────────
  async function injectFile(fileData) {
    const { data: base64Data, name, mime } = fileData;

    // 1. Convert Base64 -> File
    const byteCharacters = atob(base64Data);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: mime });
    const file = new File([blob], name, { type: mime });

    // 2. Find input area
    let inputEl = await findInputArea();
    if (!inputEl) return;
    inputEl.focus();

    // 3. Paste
    const dt = new DataTransfer();
    dt.items.add(file);
    const pasteEvent = new ClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true
    });
    inputEl.dispatchEvent(pasteEvent);
    console.log(`[BNP NotebookLM] File '${name}' pasted`);
  }

  async function findInputArea() {
    let inputEl = null;
    for (let i = 0; i < 10; i++) {
      const el = document.querySelector('textarea, div[contenteditable="true"], [role="textbox"]');
      if (el) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 10) {
          inputEl = el;
          break;
        }
      }
      await delay(150); // SPEED: was 300ms
    }
    return inputEl;
  }

  // ─── Prompt Injection ───────────────────────────────────────
  async function injectPrompt(text) {
    // ⚡ BANE-V3 Injection Header (Reference-Only — content lives in uploaded sources)
    const systemHeader = `[MANDATORY RULES] MANDATORY_RULES.txt\n` +
      `[DEPLOYMENT_GUIDE] AUTONOMOUS_DEPLOYMENT_GUIDE.md\n` +
      `[MCP_TOOL_GUIDE] MCP_TOOLS_DOCUMENTATION.md\n` +
      `[EXECUTION COMMAND]\n`;

    // Ensure we don't double-inject if the pipeline already sent it
    const hasExistingHeader = text.includes("[MANDATORY RULES]") ||
      text.includes("[KNOWLEDGE BASE]") ||
      text.includes("[EXECUTION COMMAND]");

    const finalPrompt = hasExistingHeader ? text : (systemHeader + text);

    // Ensure tab is visually active if possible
    window.focus();

    let inputEl = null;

    // Aggressively scan the DOM to find the *chat* input box on NotebookLM
    // The correct chat box in NotebookLM usually has placeholder "Start typing..." or role="textbox" at the bottom
    for (let i = 0; i < 20; i++) {
      const editables = document.querySelectorAll('textarea, input, [contenteditable="true"], [role="textbox"], .chat-input, .input-area');

      let validInputs = [];
      for (const ta of editables) {
        const rect = ta.getBoundingClientRect();
        // Check if it's visible
        if (rect.width > 50 && rect.height > 10) {
          const placeholder = (ta.placeholder || ta.getAttribute('data-placeholder') || ta.getAttribute('aria-label') || "").toLowerCase();

          // 1. Exact match for the chat box placeholder
          if (placeholder.includes("typing") || placeholder.includes("chat") || placeholder.includes("message")) {
            inputEl = ta;
            // NotebookLM heavily relies on a specific class for the main chat
            if (ta.closest('mwc-textarea') || ta.tagName === 'TEXTAREA' || ta.getAttribute('contenteditable')) {
              break;
            }
          }

          // Add to fallbacks if it looks like a valid text entry that isn't search
          if (!placeholder.includes("search") && !placeholder.includes("source")) {
            validInputs.push(ta);
          }
        }
      }

      if (inputEl) break; // Found by placeholder or aria

      // 2. Fallback: NotebookLM's true chat box is almost always the lowest text box vertically on the page
      if (validInputs.length > 0) {
        validInputs.sort((a, b) => b.getBoundingClientRect().y - a.getBoundingClientRect().y);
        inputEl = validInputs[0];
        break;
      }

      await delay(500);
    }

    if (!inputEl) {
      sendErrorResponse(currentRequestId, "Fatal: Could not find NotebookLM chat box.");
      return;
    }

    // Capture the old response before we do anything
    const previousResponseText = getLatestResponse();
    // Track model turn count BEFORE sending — used to detect genuinely NEW responses
    const previousTurnCount = document.querySelectorAll('.chat-message.model, [data-message-role="model"], [data-message-author-role="1"], .model-response-container, .response-message').length;
    // Track body text length — universal growth signal that works regardless of DOM structure
    const previousBodyLength = document.body.innerText.length;
    console.log(`[BNP NotebookLM] Previous turn count: ${previousTurnCount}, body length: ${previousBodyLength}`);

    // If it's a web component like mwc-textarea, the real textarea might be inside its shadow root
    let actionableInput = inputEl;
    if (inputEl.shadowRoot) {
      let innerTextarea = inputEl.shadowRoot.querySelector('textarea, input');
      if (innerTextarea) actionableInput = innerTextarea;
    } else if (inputEl.tagName === 'MWC-TEXTAREA') {
      let innerTextarea = inputEl.querySelector('textarea, input');
      if (innerTextarea) actionableInput = innerTextarea;
    }

    // Focus heavily
    actionableInput.focus();
    actionableInput.click?.();
    await delay(100);

    // NotebookLM strictly uses an Angular/Lit property setter or exact keyboard events.
    // The most reliable way is simulating exact keystrokes so its listener fires.

    // 1. Clear text
    actionableInput.value = "";
    actionableInput.textContent = "";

    // 2. Set text directly
    const success = document.execCommand("insertText", false, text);

    // Fallback if execCommand failed
    await delay(100);
    let currentInputText = (actionableInput.value || actionableInput.textContent || "").trim();
    if (!success || currentInputText.length < 5) {
      logMsg("execCommand weak, attempting direct property fallback...");
      // Force trigger native setter (Angular bypass)
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, "value"
      )?.set || Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, "value"
      )?.set;

      if (nativeInputValueSetter && (actionableInput.tagName === "TEXTAREA" || actionableInput.tagName === "INPUT")) {
        nativeInputValueSetter.call(actionableInput, text);
      } else {
        actionableInput.value = text;
        actionableInput.innerText = text;
        actionableInput.textContent = text;
      }
    }

    // 4. Send exact comprehensive event streams to fake human typing
    const eventTypes = ['keydown', 'keypress', 'input', 'keyup', 'change'];
    for (const type of eventTypes) {
      actionableInput.dispatchEvent(new Event(type, { bubbles: true, cancelable: true }));
      inputEl.dispatchEvent(new Event(type, { bubbles: true, cancelable: true }));
    }

    // Wait for the text to actually render in the box before we click send.
    // NotebookLM's Angular/Lit frameworks can be slow to sync.
    for (let i = 0; i < 12; i++) {
      const currentText = (actionableInput.value || actionableInput.textContent || "").trim();
      if (currentText.length > 0) {
        break;
      }
      await delay(100);
    }
    await delay(300); // Guard delay for final UI sync

    console.log("[BNP NotebookLM] Prompt explicitly injected and rendered, looking for send button...");

    // Find and click send button
    let sendBtn = await findSendButton(inputEl);
    if (sendBtn) {
      simulateClick(sendBtn);
      console.log("[BNP NotebookLM] Send button clicked");
    } else {
      console.log("[BNP NotebookLM] Send button not found. Triggering fallback...");
      // Fallback: press Enter
      const events = [
        new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }),
        new KeyboardEvent("keypress", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }),
        new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true })
      ];
      events.forEach(ev => inputEl.dispatchEvent(ev));
    }

    // Double check if text remained in the input box, which implies sending failed
    // SPEED: Increased delay to 3500ms to allow UI sync.
    await delay(3500);

    const checkText = (actionableInput.value || actionableInput.textContent || "").trim();
    const currentTurnCount = document.querySelectorAll('.chat-message.model, [data-message-role="model"], [data-message-author-role="1"], .model-response-container, .response-message').length;

    // Panic only if BOTH the box is still full AND no new message turn appeared
    if (checkText.length > 10 && currentTurnCount <= previousTurnCount) {
      console.warn("[BNP NotebookLM] Text remained and no new turn detected! Send failed. Panic clicking...");

      // Strategy 1: Find ANY button that looks like a send button in the whole document
      const allBtns = document.querySelectorAll('button, mwc-icon-button, [role="button"]');
      for (const b of allBtns) {
        const html = b.outerHTML.toLowerCase();
        if ((html.includes('send') || html.includes('arrow_forward') || html.includes('submit')) && !b.disabled) {
          simulateClick(b);
        }
      }

      // Strategy 2: Click the last button inside the input container's hierarchy
      let curr = actionableInput;
      for (let i = 0; i < 5; i++) {
        if (!curr.parentElement) break;
        curr = curr.parentElement;
        const nearby = curr.querySelectorAll('button, mwc-icon-button, [role="button"]');
        if (nearby.length > 0) {
          simulateClick(nearby[nearby.length - 1]);
        }
      }
    }

    // Start watching for response
    watchForResponse(previousResponseText, previousTurnCount, previousBodyLength);
  }

  // ─── Find Send Button ──────────────────────────────────────
  async function findSendButton(inputEl) {
    const selectors = [
      'button[aria-label*="Send"]',
      'button[aria-label*="send"]',
      'button[aria-label="Submit"]',
      'query-box button[type="submit"]',
      'query-box button',
      'query-box button mat-icon',
      'omnibar query-box button',
      'mwc-icon-button[icon="send"]',
      'mwc-icon-button[icon="arrow_forward"]',
      'button.send-button',
      'mat-icon-button',
      '.send-button-container button',
      'path[d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"]',
      'path[d="M3 20V14L11 12L3 10V4L22 12Z"]',
      'svg[data-icon="send"]',
      '.chat-input-send-button',
      'button[aria-label*="Chat"]',
      'button[aria-label*="message"]',
      '.send-button'
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const btn = el.closest("button") || el.closest("mwc-icon-button") || el.closest('[role="button"]') || el;
        if (btn && !btn.disabled && btn.getBoundingClientRect().width > 0) return btn;
      }
    }

    // Strategy 2: Search all icons for arrow/send text
    const allIcons = document.querySelectorAll('mat-icon, mwc-icon');
    for (const icon of allIcons) {
      const text = icon.textContent.toLowerCase();
      if (text.includes('send') || text.includes('arrow') || text.includes('forward')) {
        const btn = icon.closest('button') || icon.closest('mwc-icon-button') || icon.closest('[role="button"]');
        if (btn && !btn.disabled && btn.getBoundingClientRect().width > 0) return btn;
      }
    }

    // Strategy 3: Look closely in the same container as the input element
    if (inputEl) {
      let container = inputEl;
      for (let i = 0; i < 7; i++) { // Deep scan
        if (!container.parentElement) break;
        container = container.parentElement;

        // Priority 1: Specifically search for icon buttons that look like send buttons
        const iconBtns = container.querySelectorAll('button, mwc-icon-button, [role="button"], mat-icon-button');
        for (const b of iconBtns) {
          const html = b.outerHTML.toLowerCase();
          const rect = b.getBoundingClientRect();
          if (rect.width > 0 && (html.includes('send') || html.includes('arrow') || html.includes('submit')) && !b.disabled) {
            return b;
          }
        }
      }
    }

    return null;
  }

  // ─── Helper function for deeply simulated clicks ───────────
  function simulateClick(element) {
    if (!element) return;
    try {
      element.click();
    } catch (e) { }

    const events = ['pointerover', 'mouseover', 'pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    events.forEach(eventType => {
      const event = new MouseEvent(eventType, {
        view: window,
        bubbles: true,
        cancelable: true,
        buttons: 1,
        composed: true
      });
      element.dispatchEvent(event);
    });
  }

  // ─── Promise-based MutationObserver LLM Detection ───────────
  function waitForLLMComplete(selector, previousResponseText, previousTurnCount = 0, previousBodyLength = 0) {
    return new Promise((resolve) => {
      console.log(`[BNP NotebookLM] Engaging MutationObserver for DOM Idle detection (${previousTurnCount} prior turns, ${previousBodyLength} prior chars)...`);
      const startTime = Date.now();
      const MAX_TIMEOUT = 90000;
      const IDLE_THRESHOLD = 3500;
      const MIN_WAIT_MS = 4000;
      const BODY_GROWTH_THRESHOLD = 10; // More sensitive detection

      let idleTimer = null;
      let lastTextLength = 0;
      let hasStartedGenerating = false;

      // ── Turn-Count Detection ──
      const hasNewTurn = () => {
        const allTurns = document.querySelectorAll(
          '.chat-message.model, [data-message-role="model"], [data-message-author-role="1"], ' +
          '.model-response-container, .response-message, .assistant-message, ' +
          '.chat-message:has(button[aria-label*="Save"]), .message:has(button[aria-label*="Save"]), ' +
          '.chat-item:has(button[aria-label*="Save"]), [role="article"]:has(button[aria-label*="Save"])'
        );
        return allTurns.length > previousTurnCount;
      };

      // ── Body Text Growth Detection ──
      // Universal signal that works regardless of DOM structure
      const bodyTextGrew = () => {
        return document.body.innerText.length > previousBodyLength + BODY_GROWTH_THRESHOLD;
      };

      const finishAndResolve = (reason) => {
        if (idleTimer) clearTimeout(idleTimer);
        observer.disconnect();
        console.log(`[BNP NotebookLM] LLM Complete via: ${reason}`);

        const finalCheck = getLatestResponse();
        const textGrew = bodyTextGrew();
        const turnExists = hasNewTurn();

        // If body text grew OR a new turn appeared, trust the response
        // This bypasses isOldResponse() which fails in multi-turn NotebookLM
        if (textGrew || turnExists) {
          console.log(`[BNP NotebookLM] Trusting response (bodyGrew: ${textGrew}, newTurn: ${turnExists})`);
          resolve(finalCheck || null);
        } else {
          if (finalCheck && !isOldResponse(finalCheck, previousResponseText)) {
            resolve(finalCheck);
          } else if (reason.includes("Timeout") && finalCheck) {
            // Last ditch: if it's a timeout but we have text, return it
            console.log("[BNP NotebookLM] Timeout reached but text exists. Returning text as fallback.");
            resolve(finalCheck);
          } else {
            resolve(null);
          }
        }
      };

      // Hybrid helper to track NotebookLM's actual loading phases
      const isStillThinking = (text) => {
        if (!text) return false;
        const loadingPhrases = [
          "understanding your question", "interpreting request", "analyzing query",
          "breaking down question", "searching knowledge base", "Locating Configuration",
          "processing passages", "examining paragraphs", "retrieving relevant chunks",
          "grounding answer in sources", "correlating findings", "synthesizing insights",
          "writing response", "formatting answer", "finalizing response"
        ];
        const lower = text.toLowerCase();
        const matchPhrase = loadingPhrases.some(p => lower.includes(p));
        const matchDots = text.trim().endsWith("...") && text.length < 50;
        return (matchPhrase && text.length < 80) || matchDots;
      };

      // Check for NotebookLM's thinking animation elements (circles, boxes, dots)
      const hasThinkingAnimation = () => {
        return document.querySelector(
          'mat-spinner, [role="progressbar"], mat-progress-bar, ' +
          '.loading-indicator, .thinking-animation, .response-loading, ' +
          '[aria-busy="true"], .spinner, .loading, .loading-dots, ' +
          '.dot-flashing, .typing-indicator, mwc-circular-progress, ' +
          'mwc-linear-progress, .processing-indicator'
        ) !== null;
      };

      const resetIdleTimer = () => {
        if (idleTimer) clearTimeout(idleTimer);
        if (hasStartedGenerating) {
          idleTimer = setTimeout(() => {
            const elapsed = Date.now() - startTime;
            if (elapsed < MIN_WAIT_MS) {
              console.log(`[BNP NotebookLM] Idle fired but only ${elapsed}ms elapsed (min: ${MIN_WAIT_MS}ms). Resetting...`);
              resetIdleTimer();
              return;
            }

            if (hasThinkingAnimation()) {
              console.log("[BNP NotebookLM] Thinking animation still active. Waiting...");
              resetIdleTimer();
              return;
            }

            const resp = getLatestResponse() || "";
            if (isStillThinking(resp)) {
              console.log("[BNP NotebookLM] Idle hit, but AI is still thinking. Waiting...");
              resetIdleTimer();
              return;
            }

            finishAndResolve("DOM Idle Timeout (3500ms)");
          }, IDLE_THRESHOLD);
        }
      };

      let lastCheckTime = 0;
      const CHECK_INTERVAL = 300; // SPEED: Throttle to 300ms to prevent browser hang

      const observer = new MutationObserver(() => {
        const now = Date.now();
        if (now - lastCheckTime < CHECK_INTERVAL) return;
        lastCheckTime = now;

        if (now - startTime > MAX_TIMEOUT) {
          finishAndResolve(`Hard Timeout (${MAX_TIMEOUT / 1000}s)`);
          return;
        }

        const currentText = getLatestResponse() || "";

        // ── Generation Start Detection ──
        // Use ALL available signals: turn count, text change, animation, body growth
        if (!hasStartedGenerating) {
          const newTurnExists = hasNewTurn();
          const isNewText = currentText && !isOldResponse(currentText, previousResponseText);
          const animationActive = hasThinkingAnimation();
          const textGrew = bodyTextGrew();

          if (newTurnExists || isNewText || animationActive || textGrew) {
            hasStartedGenerating = true;
            console.log(`[BNP NotebookLM] Detected new generation start! (newTurn: ${newTurnExists}, newText: ${isNewText}, animation: ${animationActive}, bodyGrew: ${textGrew})`);
            resetIdleTimer();
          }
        }

        if (hasStartedGenerating) {
          const stopBtn = document.querySelector('button[aria-label*="Stop"], button[aria-label*="stop"]');
          const isTypingDiv = hasThinkingAnimation();

          if (currentText.length !== lastTextLength) {
            lastTextLength = currentText.length;
            resetIdleTimer();
          } else if (!stopBtn && !isTypingDiv) {
            // Let the idle timer confirm it
          }
        }
      });

      const targetNode = document.querySelector(selector) || document.body;
      observer.observe(targetNode, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['disabled', 'class', 'style', 'aria-busy']
      });

      // Failsafe global timer
      setTimeout(() => finishAndResolve("Failsafe Hard Timeout (90s)"), MAX_TIMEOUT);
    });
  }

  // ─── Response Flow Execution ────────────────────────────────
  async function watchForResponse(previousResponseText, previousTurnCount = 0, previousBodyLength = 0) {
    // 1. Wait for response container via waitForLLMComplete
    const rawFinalText = await waitForLLMComplete("body", previousResponseText, previousTurnCount, previousBodyLength);

    if (!rawFinalText) {
      sendErrorResponse(currentRequestId, "Timeout: AI did not write a new response.");
      return;
    }

    console.log("[BNP NotebookLM] Stability reached. Waiting for interactive chips...");

    // ⚡ Dynamic delayed harvesting to handle both high-speed and slow internet
    let suggestions = [];
    for (let i = 0; i < 8; i++) {
      suggestions = getSuggestedQueries();
      if (suggestions.length > 0) break;
      await delay(500); // from utils/delay helper
    }

    // Try Copy button first for perfect formatting
    try {
      const qualityText = await captureTextViaCopyButton();
      const finalResult = qualityText || rawFinalText;
      console.log("[BNP NotebookLM] Response Cluster Ready. Sending...");
      sendResponse(currentRequestId, finalResult, suggestions);
    } catch (e) {
      sendResponse(currentRequestId, rawFinalText, suggestions);
    }
  }

  // ─── Extract Interactive Suggestions (Buttons) ──────────────
  function getSuggestedQueries() {
    console.log("[BNP NotebookLM] Harvesting high-speed AI chips...");
    const suggestions = [];

    // Broad selectors for any pill-like interactive elements in the chat area
    const selectors = [
      '.suggestion-chip',
      '.quantum-chip',
      'mwc-button',
      'button',
      '[role="button"]',
      '.chip-text'
    ];

    const allElements = document.querySelectorAll(selectors.join(','));
    console.log(`[BNP NotebookLM] Total elements examined: ${allElements.length}`);

    for (const el of allElements) {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || el.textContent).trim();

      // VISIBILITY & CONTENT FILTERS
      const isVisible = rect.height > 5 && rect.width > 20;
      const isButtonLike = text.length > 12 && text.length < 120; // Suggested queries are usually medium-length sentences

      // HEURISTIC: Suggested queries in NotebookLM usually don't have icons inside them 
      // and are at the bottom of the viewport area
      const isNotSystem = !["save", "copy", "good", "bad", "feedback", "citation", "source", "helpful", "edit", "share", "settings", "language", "add", "arrow", "keyboard", "forward", "down", "up", "back", "send", "attach", "mic", "stop", "menu"].some(word => text.toLowerCase().includes(word));

      // Location check: Ensure it's in the bottom half of the screen (chat area)
      const inChatArea = rect.top > window.innerHeight * 0.3;

      if (isVisible && isButtonLike && isNotSystem && inChatArea) {
        // Clean any potential icon font names that might leak in
        let cleanText = text.replace(/[\n\r]/g, " ").trim();
        if (cleanText.length > 5) {
          suggestions.push(cleanText);
        }
      }
    }

    // Take the last 3 (bottom-most) unique suggestions
    // Filter out more aggressively: skip file names, source counts, etc.
    const uniqueSuggestions = [...new Set(suggestions)]
      .filter(s => {
        const low = s.toLowerCase();
        // Exclude citations (numbers only), file extensions, and generic UI labels
        if (/^\s*\d+\s*$/.test(s)) return false;
        if (low.includes('.pdf') || low.includes('.docx') || low.includes('.txt')) return false;
        if (low.includes('presentation') || low.includes('drive_') || low.includes('tap to ask') || low.includes('tap to send')) return false;
        // Suggested queries are usually complete sentences or phrases
        return s.length > 10;
      })
      .slice(-3);

    console.log(`[BNP NotebookLM] Successfully harvested ${uniqueSuggestions.length} chips:`, uniqueSuggestions);
    return uniqueSuggestions;
  }

  // ─── High Quality Copy Strategy ─────────────────────────────
  async function captureTextViaCopyButton() {
    try {
      const lastTurn = document.querySelectorAll(
        '.chat-message.model, [data-message-role="model"], ' +
        '.chat-message:has(button[aria-label*="Save"]), .message:has(button[aria-label*="Save"])'
      );
      if (lastTurn.length === 0) return null;

      const turn = lastTurn[lastTurn.length - 1];
      // Focus turn to ensure the button is "visible" for click
      turn.scrollIntoView({ behavior: 'smooth', block: 'center' });

      let copyBtn = turn.querySelector(
        'button[aria-label*="Copy"], ' +
        '[aria-label*="Copy model response"], ' +
        'mwc-icon-button[icon*="copy"], ' +
        'button[mattooltip*="Copy"], ' +
        '[aria-label*="copy message"], ' +
        '.copy-button, ' +
        'mat-icon[data-icon*="copy"], ' +
        'mat-icon[aria-label*="Copy"]'
      );

      // Fallback: search for "copy_all" icon text
      if (!copyBtn) {
        const icons = turn.querySelectorAll('mat-icon');
        for (const icon of icons) {
          if (icon.textContent.includes('copy_all')) {
            copyBtn = icon.closest('button') || icon;
            break;
          }
        }
      }

      if (copyBtn) {
        simulateClick(copyBtn);
        await delay(400); // Wait for copy event
        if (capturedClipboardText && capturedClipboardText.length > 20) {
          console.log("[BNP NotebookLM] Copy Success (MD preserved)");
          return capturedClipboardText;
        }
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  // Global listener to 'steal' the text being copied when we click the button
  window.addEventListener('copy', (e) => {
    const text = window.getSelection().toString();
    // If we're clicking the copy button, the text is usually in the clipboardData
    const clipboardText = e.clipboardData?.getData('text/plain');
    if (clipboardText) {
      capturedClipboardText = clipboardText;
    }
  }, true);

  // ─── Helper for old text fuzzy matching ─────────────────────
  function isOldResponse(newText, oldText) {
    if (!oldText) return false;
    const cleanNew = newText.trim().replace(/\s+/g, ' ');
    const cleanOld = oldText.trim().replace(/\s+/g, ' ');

    if (cleanNew === cleanOld) return true;

    // Check if new text is just the old text with minor additions (like citation dots)
    if (cleanNew.startsWith(cleanOld) && cleanNew.length < cleanOld.length + 10) {
      return true;
    }

    return false;
  }

  // ─── Extract Latest Response ────────────────────────────────

  // Smart DOM parser to preserve bullet points and purge citation chips
  function extractRichText(element) {
    if (!element) return "";

    // Helper to traverse DOM and build Markdown string
    function walk(node) {
      if (node.nodeType === 3) return node.textContent;
      if (node.nodeType !== 1) return "";

      const tagName = node.tagName.toLowerCase();

      // Filter UI junk
      if (node.classList.contains('citation') ||
        node.classList.contains('source-chip') ||
        tagName === 'button' ||
        tagName === 'sup' ||
        node.getAttribute('aria-label')?.toLowerCase().includes('citation')) {
        return "";
      }

      let content = "";
      for (const child of node.childNodes) {
        content += walk(child);
      }

      const trimmed = content.trim();
      if (!trimmed) return "";

      // 1. Headers (Standard or Styled)
      if (/^h[1-6]$/.test(tagName) || node.classList.contains('header') || node.classList.contains('title')) {
        return `\n\n**${trimmed}**\n\n`;
      }

      // 2. List Items
      if (tagName === 'li') return `\n• ${trimmed}`;

      // 3. Structural Blocks
      if (tagName === 'p' || tagName === 'div' || tagName === 'article' || tagName === 'section') {
        // If the block contains ONLY bold text, it's likely a header
        if (node.children.length === 1 && (node.children[0].tagName === 'B' || node.children[0].tagName === 'STRONG')) {
          return `\n\n**${trimmed}**\n\n`;
        }
        return `\n${trimmed}\n`;
      }

      // 4. Inline formatting
      if (tagName === 'b' || tagName === 'strong') return ` **${trimmed}** `;
      if (tagName === 'br') return "\n";

      return content;
    }

    let text = walk(element);

    // Final cleanup of redundant newlines and UI artifacts
    text = text.replace(/\[\d+(?:[\s,-]+\d+)*\]/g, "");
    text = text.replace(/\d+\s+sources?/gi, "");
    text = text.replace(/(\r?\n){3,}/g, '\n\n');

    return text.trim();
  }

  function getLatestResponse() {
    const loadingPatterns = [
      "finding", "checking", "digging", "assessing", "searching", "reading", "sifting",
      "analyzing", "thinking", "composing", "generating", "drafting", "refining",
      "reviewing", "editing", "correcting", "finalizing", "delivering", "confirming", "summarizing"
    ];

    function isPureLoadingChip(text) {
      if (!text || text.length > 80) return false;
      const lower = text.toLowerCase();
      return loadingPatterns.some(p => lower.includes(p)) || text.endsWith("...");
    }

    // ★ Detect if text is from the injected system prompt (user message)
    // IMPORTANT: Must NOT reject the AI's JSON tool call responses like { "call_tool": ... }
    function isInjectedUserMessage(text) {
      if (!text) return false;
      // System prompt documentation markers — things that only appear in the INJECTED header,
      // never in legitimate AI responses. Deliberately excludes "call_tool" patterns
      // because the AI's tool call responses legitimately contain those.
      const promptMarkers = [
        "SYSTEM TOOLS AVAILABLE",
        "CRITICAL EXECUTION RULES",
        "Response Format for Tool Calls",
        "[EXECUTION COMMAND]",
        "DO NOT say you cannot access the filesystem",
        "DO NOT add any explanation text before or after the JSON block",
        "[TOOL RESULT:",
        "BANE: Iteration"
      ];
      // Require 2+ markers to match — a full injection header has many,
      // while a single AI response or tool call has zero or one.
      const matchCount = promptMarkers.filter(m => text.includes(m)).length;
      if (matchCount >= 2) return true;

      // Check for platform/execution tags (both must be present = injection header)
      if (/\[PLATFORM:\s*\w+\]/.test(text) && /\[USER_ID:\s*\d+\]/.test(text)) return true;

      return false;
    }

    // ─── Strategy 1: Known model message selectors ───
    const modelSelectors = [
      // Standard chat roles
      '.chat-message.model',
      '[data-message-role="model"]',
      '[data-message-author-role="1"]',
      // Google/Angular/Lit common patterns
      '.response-message',
      '.chat-response',
      '.model-response-container',
      '.assistant-content',
      // NotebookLM Specifics (Save to note button is a strong anchor)
      '.chat-message:has(button[aria-label*="Save"])',
      '.message:has(button[aria-label*="Save"])',
      '.chat-item:has(button[aria-label*="Save"])',
      '[role="article"]:has(button[aria-label*="Save"])',
      '.model-response-text',
      '.response-content',
      // Generic message containers (filtered below)
      '.message-content',
      '[data-source-type="model"]',
      '.model-message',
      '.ai-response',
      '.ai-message',
      '[author="model"]',
      '[author="assistant"]'
    ];

    for (const sel of modelSelectors) {
      const els = document.querySelectorAll(sel);
      if (els.length > 0) {
        let fallback = null;
        for (let i = els.length - 1; i >= 0; i--) {
          const text = extractRichText(els[i]);
          if (!isInjectedUserMessage(text)) {
            if (!fallback) fallback = text;
            if (!isPureLoadingChip(text)) {
              return cleanResponseText(text);
            }
          }
        }
        if (fallback) return cleanResponseText(fallback);
      }
    }

    // ─── Strategy 2: Chat log containers ───
    const logContainers = document.querySelectorAll(
      'chat-panel, .chat-panel, div[role="log"], .chat-history, .chat-container, .conversation-container, ' +
      '.chat-scroll-container, [data-chat-messages], .chat-thread'
    );
    for (const container of logContainers) {
      const children = container.children;
      for (let i = children.length - 1; i >= 0; i--) {
        const text = extractRichText(children[i]);
        if (!isInjectedUserMessage(text) && !isPureLoadingChip(text)) {
          return cleanResponseText(text);
        }
      }
    }

    // ─── Strategy 3: Shadow DOM drilling ───
    const customElements = document.querySelectorAll('mwc-list-item, mwc-textarea, any-message-wrapper');
    for (const ce of customElements) {
      if (ce.shadowRoot) {
        const log = ce.shadowRoot.querySelector('[role="log"], .content, .message');
        if (log && (log.innerText || log.textContent).length > 5) {
          const text = extractRichText(log);
          if (!isPureLoadingChip(text) && !isInjectedUserMessage(text)) return cleanResponseText(text);
        }
      }
    }

    // ⚡ PERFORMANCE FIX: Focus on semantic containers first to avoid scanning thousands of divs
    const viewportWidth = window.innerWidth;
    const leftBound = viewportWidth * 0.05;
    const rightBound = viewportWidth * 0.85;

    const containerSelectors = [
      '.chat-message', '.message', 'article', 'section',
      '[role="article"]', '.response', '.model-response',
      '.assistant-message', '.chat-item'
    ];

    const candidates = Array.from(document.querySelectorAll(containerSelectors.join(','))).filter(el => {
      const rect = el.getBoundingClientRect();
      if (rect.width < 150 || rect.height < 15) return false;
      // Viewport-relative position filtering (instead of hardcoded pixels)
      if (rect.left < leftBound || rect.left > rightBound) return false;
      // Skip off-screen elements
      if (rect.top < 0 || rect.top > window.innerHeight) return false;
      const innerText = extractRichText(el);
      if (innerText.length < 10) return false;
      // Instead of rejecting containers that have injection markers,
      // clean the text first and check if meaningful content remains
      const cleaned = cleanResponseText(innerText);
      if (cleaned.length < 10) return false;
      // Only reject if the CLEANED text is still predominantly injection content
      if (isInjectedUserMessage(cleaned)) return false;
      return true;
    });

    if (candidates.length > 0) {
      // Sort by Y position descending → bottom-most (most recent) first
      candidates.sort((a, b) => b.getBoundingClientRect().y - a.getBoundingClientRect().y);
      for (const el of candidates) {
        const text = extractRichText(el);
        // Filter out NotebookLM footer UI elements
        const isUIFragment = /^\d+\s*sources?$/i.test(text) ||
          /^(arrow_forward|save to note|start typing|notebooklm can be inaccurate)$/i.test(text.toLowerCase().trim()) ||
          text.length < 15;
        if (!isUIFragment && !isPureLoadingChip(text)) {
          return cleanResponseText(text);
        }
      }
      // Last resort — take absolute bottom element (but NOT if it's a UI fragment)
      const fallbackText = extractRichText(candidates[0]);
      if (fallbackText.length > 30 && !/^\d+\s*sources?$/i.test(fallbackText)) {
        return cleanResponseText(fallbackText);
      }
    }

    return null;
  }

  // ─── Clean Citations/Badges ──────────────────────────────────
  function cleanResponseText(text) {
    if (!text) return "";

    let cleaned = text;

    // 0. ★ CRITICAL: Strip the entire BNP system prompt if it was accidentally scraped.
    // The Chrome extension sometimes grabs the user's injected message (which contains the full system prompt)
    // alongside or instead of the model's response. We must remove this entire block.
    // Pattern: starts with "SYSTEM TOOLS AVAILABLE" and runs until the "[EXECUTION COMMAND]" + "USER:" line.
    cleaned = cleaned.replace(
      /(?:#\s*)?SYSTEM TOOLS AVAILABLE[\s\S]*?\[EXECUTION COMMAND\][\s\S]*?(?:USER:\s*.+?\n)/gi,
      ""
    );
    // Also strip if we only got up to "REMEMBER:" without the full [EXECUTION COMMAND] block
    cleaned = cleaned.replace(
      /(?:#\s*)?SYSTEM TOOLS AVAILABLE[\s\S]*?REMEMBER:[\s\S]*?(?:persona format\.|persona format|your persona format\.?\s*\n)/gi,
      ""
    );
    // Strip standalone [EXECUTION COMMAND] blocks and platform tags
    cleaned = cleaned.replace(/\[KNOWLEDGE BASE\][\s\S]*?\[USER_ID: \d+\]\s*USER:.*?\n/gi, "");
    cleaned = cleaned.replace(/\[EXECUTION COMMAND\]\s*/gi, "");
    cleaned = cleaned.replace(/\[KNOWLEDGE BASE\] BANE_CONTEXT_FILES\/BANE_NLP_BRAIN_knowledge\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[MANDATORY RULES\] MANDATORY_RULES\.txt\s*/gi, "");
    cleaned = cleaned.replace(/\[WORKSPACE MAP\] WORKSPACE_ARCHITECTURE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[PROJECT CONTEXT\] ACTIVE_PROJECTS_CONTEXT\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[SCENARIOS GUIDE\] BANE_SCENARIOS\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[DEPLOYMENT_GUIDE\] AUTONOMOUS_DEPLOYMENT_GUIDE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[MCP_TOOL_GUIDE\] MCP_TOOLS_DOCUMENTATION\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[PLATFORM:\s*\w+\]\s*/gi, "");
    cleaned = cleaned.replace(/\[USER_ID:\s*\d+\]\s*/gi, "");

    // 1. Remove Protocol Headers & Identity Blocks
    cleaned = cleaned.replace(/\[PIPELINE:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[SOURCE:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[TARGET:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[STYLING:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[IDENTITY_PROTOCOL_ACTIVE\][\s\S]*?\[\/IDENTITY_PROTOCOL_ACTIVE\]/gi, "");
    cleaned = cleaned.replace(/\[INSTRUCTION:[\s\S]*?\]/gi, "");

    // 2. Remove authorship labels
    cleaned = cleaned.replace(/^(Gemini|You) said/gi, "");
    cleaned = cleaned.replace(/\s(Gemini|You) said/gi, "");

    // 3. Remove ALL citation artifacts and UI labels
    cleaned = cleaned.replace(/\[cite_start\]/gi, "");
    cleaned = cleaned.replace(/\[cite_end\]/gi, "");
    cleaned = cleaned.replace(/\[cite:\s*[\d,\s]+\]/gi, "");
    cleaned = cleaned.replace(/\s*\[\s*\d+(?:\s*,\s*\d+)*\s*\]/g, "");

    // 3b. Remove 'more_horiz' and UI artifacts (NotebookLM icon leak)
    cleaned = cleaned.replace(/more_horiz\.?\s*/g, "");
    cleaned = cleaned.replace(/\bmore_horiz\b/g, "");

    // 4. Remove unbracketed citation digits (phantom numbers from UI)
    // 4a. Strip entire lines that are just citation numbers (e.g. "1" or "2 3")
    cleaned = cleaned.replace(/^\s*\d+(?:\s+\d+)*\s*$/gm, "");

    // 4b. Strip trailing numbers at end of line/phrase
    cleaned = cleaned.replace(/(\!|\?|\:|\w)(\s*)(\d+(?:\s+\d+)*)(\s*)($|(?=\n))/g, "$1$2$5");

    // 5. Clean up rogue whitespace and punctuation debris
    cleaned = cleaned.replace(/\s+([.,;:!?])/g, "$1");
    cleaned = cleaned.replace(/(\r?\n){3,}/g, "\n\n"); // Normalize spacing

    // 6. Protect design: only clean excessive triple spaces
    cleaned = cleaned.replace(/[ ]{3,}/g, '  ');

    // 7. Strip NotebookLM-specific UI artifacts that leak from DOM
    cleaned = cleaned.replace(/^\s*\d+\s*sources?\s*$/gmi, "");
    cleaned = cleaned.replace(/\barrow_forward\b/gi, "");
    cleaned = cleaned.replace(/\bquery_builder\b/gi, "");
    cleaned = cleaned.replace(/\bSave to note\b/gi, "");
    cleaned = cleaned.replace(/\bShare\b/gi, "");
    cleaned = cleaned.replace(/NotebookLM can be inaccurate[^\n]*/gi, "");

    // 8. FINAL POLISH: Ensure double newlines between blocks and remove trailing debris
    cleaned = cleaned.replace(/(\r?\n){3,}/g, "\n\n");
    cleaned = cleaned.replace(/\s+$/g, "");

    return cleaned.trim();
  }

  // ─── Send Response Back ─────────────────────────────────────
  function sendResponse(requestId, text, suggestions = []) {
    const responsePayload = {
      pipeline: PIPELINE_NAME,
      id: requestId,
      type: "response",
      source: "notebooklm",
      timestamp: new Date().toISOString(),
      payload: {
        text: text,
        suggestions: suggestions
      },
    };

    window.dispatchEvent(
      new CustomEvent("bnp-response", { detail: responsePayload })
    );
  }

  function sendErrorResponse(requestId, errorMessage) {
    sendResponse(requestId, `[BNP Error] ${errorMessage}`);
  }

  // ─── Utility Functions ──────────────────────────────────────
  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitForElement(selectors, timeoutMs = 10000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) return el;
      }
      await delay(250);
    }
    return null;
  }

  console.log("[BNP NotebookLM] Content script ready");
})();
