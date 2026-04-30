/**
 * BNP Content Script — ChatGPT
 * ==============================
 * Handles prompt injection and response capture on chatgpt.com.
 *
 * INJECTION MODEL: TEXT-ONLY (No File Attachments)
 * ================================================
 * Unlike the Gemini content script, ChatGPT uses a pure text prompt injection:
 *   - HEADER: Summarized AI_SKILLS.md persona directives (built by bane_core.py)
 *   - FOOTER: The user's actual query/intent
 *   - NO file paste/attachment injection
 *
 * Strategy:
 *   1. Listen for "bnp-prompt" events from the WebSocket bridge
 *   2. Find ChatGPT's input textarea (#prompt-textarea or contenteditable)
 *   3. Inject the full prompt text (header + context + footer query)
 *   4. Trigger the send action
 *   5. Observe the DOM for the AI response
 *   6. Dispatch a "bnp-response" event with the response text
 */

(function () {
  "use strict";

  const PIPELINE_NAME = "BNP";
  const POLL_INTERVAL_MS = 400;
  const RESPONSE_TIMEOUT_MS = 290000; // slightly less than Python timeout (300s)

  let currentRequestId = null;
  let responseObserver = null;

  // ─── Notify Background ──────────────────────────────────────
  chrome.runtime.sendMessage({
    type: "BNP_CONTENT_READY",
    target: "chatgpt",
  });

  console.log("[BNP ChatGPT] Content script loaded.");

  // ─── Request Queue to Prevent Overlaps ────────────────────────
  const promptQueue = [];
  const processedRequestIds = new Set();
  let isProcessingPrompt = false;

  window.addEventListener("bnp-prompt", (event) => {
    const data = event.detail;
    if (!data.id) return;
    
    // De-duplicate: If we've already queued or processed this exact ID, ignore it.
    if (processedRequestIds.has(data.id)) {
      console.log(`[BNP ChatGPT] Ignoring duplicate prompt ID: ${data.id}`);
      return;
    }
    processedRequestIds.add(data.id);
    
    // Manage set size (LRU-ish)
    if (processedRequestIds.size > 50) {
      const first = processedRequestIds.values().next().value;
      processedRequestIds.delete(first);
    }

    promptQueue.push(data);
    processNextPrompt();
  });

  window.addEventListener("bnp-signal", (event) => {
    const action = event.detail?.action;
    if (action === "new_conversation") {
      console.log("[BNP ChatGPT] Signal: Starting new conversation...");
      window.location.href = "https://chatgpt.com/";
    } else if (action === "navigate") {
      const url = event.detail?.url;
      if (url) {
        console.log("[BNP ChatGPT] Signal: Navigating to", url);
        window.location.href = url;
      }
    }
  });

  async function processNextPrompt() {
    if (isProcessingPrompt || promptQueue.length === 0) return;
    isProcessingPrompt = true;

    const data = promptQueue.shift();

    if (data.target !== "chatgpt") {
      console.log("[BNP ChatGPT] Ignoring prompt for different target:", data.target);
      isProcessingPrompt = false;
      processNextPrompt();
      return;
    }

    const message = data.payload?.message;
    if (!message) {
      console.error("[BNP ChatGPT] No message in payload");
      isProcessingPrompt = false;
      processNextPrompt();
      return;
    }

    currentRequestId = data.id;
    console.log(`[BNP ChatGPT] Processing prompt (${currentRequestId}):`, message.substring(0, 80));

    const logMsg = (text) => {
      console.log(`[BNP ChatGPT] ${text}`);
      window.dispatchEvent(new CustomEvent("bnp-log", { detail: { source: "ChatGPT", text } }));
      chrome.runtime.sendMessage({ type: "BNP_LOG", source: "ChatGPT", text });
    };

    // --- PRE-SEED IMAGE TRACKER ---
    // If we just refreshed or started a new request, we MUST ignore all images 
    // that already exist on the screen to prevent hallucinating old images!
    const existingImages = document.querySelectorAll('img');
    let preSeedCount = 0;
    existingImages.forEach(img => {
      if (img.src && typeof isValidForResult === 'function' && isValidForResult(img, null)) {
        sentImageUrls.add(img.src);
        preSeedCount++;
      } else if (img.src) {
        sentImageUrls.add(img.src); // Aggressively block all existing sources just to be safe
        preSeedCount++;
      }
    });
    if (preSeedCount > 0) logMsg(`Pre-seeded image tracker with ${preSeedCount} existing images to prevent leakages.`);

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // INJECTION: Files + Text
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    try {
      const files = data.payload?.files || (data.payload?.file ? [data.payload.file] : []);
      let attachedFilesCount = 0;

      if (files.length > 0) {
        logMsg(`[ATTACHMENT] Found ${files.length} file(s). Attempting to upload...`);
        for (const file of files) {
          try {
            const success = await injectFile(file, logMsg);
            if (success) attachedFilesCount++;
          } catch (e) {
            logMsg(`[WARN] File upload failed for '${file.name}', continuing with text prompt.`);
          }
        }
      }
      await injectPrompt(message, logMsg, attachedFilesCount);
    } catch (err) {
      console.error("[BNP ChatGPT] Injection failed:", err);
      sendErrorResponse(currentRequestId, `Injection failed: ${err.message}`);
    }
  }

  // ─── File Injection ─────────────────────────────────────────
  async function injectFile(fileData, logMsg) {
    const { data: base64Data, name, mime } = fileData;

    try {
      // 1. Convert Base64 payload to File blob
      const byteCharacters = atob(base64Data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: mime });
      const file = new File([blob], name, { type: mime });

      // 2. Find ChatGPT's input area
      let inputEl = await findInputArea();
      if (!inputEl) {
        logMsg("[ERROR] Could not find input area for file upload.");
        return;
      }

      inputEl.focus();
      inputEl.click?.();
      await delay(100);

      // 3. Simulate Clipboard Paste event with the File
      const dt = new DataTransfer();
      dt.items.add(file);

      const pasteEvent = new ClipboardEvent('paste', {
        clipboardData: dt,
        bubbles: true,
        cancelable: true
      });

      inputEl.dispatchEvent(pasteEvent);
      console.log(`[BNP ChatGPT] Successfully pasted file '${name}' into ChatGPT.`);
      await delay(1000); // Wait for ChatGPT to process the file upload
      return true;
    } catch (err) {
      logMsg(`[ERROR] Injection failed for file '${name}': ${err.message}`);
      return false;
    }
  }

  // ─── Find ChatGPT Input Area ──────────────────────────────────
  async function findInputArea() {
    let inputEl = null;
    const selectors = [
      '#prompt-textarea',                              // ChatGPT's main textarea (ProseMirror)
      'div[contenteditable="true"][id="prompt-textarea"]',
      'div[contenteditable="true"]',                    // Generic contenteditable fallback
      'textarea[data-id="root"]',                      // Alternative textarea
      'textarea',                                       // Absolute fallback
    ];

    for (let attempt = 0; attempt < 15; attempt++) {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 50 && rect.height > 10) {
            inputEl = el;
            break;
          }
        }
      }
      if (inputEl) break;
      await delay(400);
    }
    return inputEl;
  }

  // ─── Prompt Injection ───────────────────────────────────────
  async function injectPrompt(text, logMsg, attachedFilesCount = 0) {
    let inputEl = await findInputArea();

    if (!inputEl) {
      sendErrorResponse(currentRequestId, "Fatal: Could not find ChatGPT input box. Please ensure the page is loaded.");
      return;
    }

    logMsg("Input area found. Injecting prompt...");

    // Force focus
    inputEl.focus();
    inputEl.click?.();
    await delay(100);

    // Clear existing content - ONLY if no files were attached. 
    // Clearing innerHTML on ProseMirror nodes deletes the file upload chips!
    if (attachedFilesCount === 0) {
      if (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT") {
        inputEl.value = "";
      } else {
        inputEl.innerHTML = "";
      }
    }
    await delay(50);

    // ─── ROBUST 3-TIER DOM INJECTION ───
    const expectedLen = text.length;

    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set ||
                                   Object.getOwnPropertyDescriptor(window.HTMLDivElement.prototype, 'innerText')?.set;
    
    if (nativeInputValueSetter && (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT")) {
      logMsg("Using React nativeInputValueSetter bypass...");
      nativeInputValueSetter.call(inputEl, text);
      
      // Dispatch input event so React picks up the change
      const ev = new Event('input', { bubbles: true, cancelable: true });
      ev.simulated = true;
      inputEl.dispatchEvent(ev);
    } else {
      // Fallback for non-React/contenteditable (ProseMirror)
      logMsg("Using ClipboardEvent paste for ProseMirror injection...");
      const dt = new DataTransfer();
      dt.setData('text/plain', text);
      const pasteEvent = new ClipboardEvent('paste', {
        clipboardData: dt,
        bubbles: true,
        cancelable: true
      });
      inputEl.dispatchEvent(pasteEvent);
      
      await delay(100);
      let currentText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
      
      // 2. Fallback: Direct property mutation if paste failed or was truncated
      if (currentText.length < expectedLen * 0.8) {
        logMsg("Paste weak/truncated, attempting direct property fallback...");
        if (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT") {
          inputEl.value = text;
        } else {
          inputEl.innerText = text;
        }
        inputEl.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
        await delay(25);
        currentText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
      }

      // 3. Final Fallback: execCommand (can sometimes truncate at newlines, so we do it last)
      if (currentText.length < expectedLen * 0.8) {
        document.execCommand("insertText", false, text);
        inputEl.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
      }
    }

    // Special KeyboardEvent for the last character to ensure the "Send" button enables
    inputEl.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    inputEl.dispatchEvent(new KeyboardEvent("keyup", { key: " ", bubbles: true }));

    // Final verification loop (fast)
    let currentText = "";
    for (let i = 0; i < 5; i++) {
      currentText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
      if (currentText.length > text.length * 0.5) break; 
      await delay(50);
    }
    await delay(50);

    // Snapshot current state BEFORE sending
    const previousTurnCount = document.querySelectorAll('[data-message-author-role="assistant"], [data-testid^="conversation-turn-"]').length;
    const previousResponseText = getLatestResponse();
    const previousBodyLength = document.body.innerText.length;
    logMsg("Prompt injected. Looking for send button...");

    // Find and wait for the send button to become active
    let sendBtn = await findSendButton(inputEl);

    for (let u = 0; u < 10; u++) {
      const isUploading = document.querySelector('progress, circle, [class*="uploading"], [class*="Upload"], [aria-valuenow]');
      const isBtnReady = sendBtn && !sendBtn.disabled && !sendBtn.hasAttribute('disabled');

      if (isBtnReady && !isUploading) {
        break;
      }
      await delay(200);
      sendBtn = await findSendButton(inputEl); // Refresh reference
    }

    if (sendBtn && !sendBtn.disabled) {
      simulateClick(sendBtn);
      logMsg("Send button clicked.");
    } else {
      logMsg("Send button not found. Pressing Enter...");
      const enterEvent = new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        which: 13,
        bubbles: true,
      });
      inputEl.dispatchEvent(enterEvent);
    }

    // Verify text was sent (box should be empty now)
    await delay(800); 
    
    const checkText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
    const currentTurnCount = document.querySelectorAll('[data-message-author-role="assistant"], [data-testid^="conversation-turn-"]').length;
    
    // Panic only if BOTH the box is still full AND no new message turn appeared
    if (checkText.length > 10 && currentTurnCount <= previousTurnCount) {
      logMsg("Text remained and no new turn detected! Panic clicking send buttons...");
      const buttons = document.querySelectorAll('button, [role="button"]');
      for (const b of buttons) {
        const html = b.outerHTML.toLowerCase();
        if ((html.includes('send') || html.includes('submit')) && !b.disabled) {
          simulateClick(b);
          await delay(200);
        }
      }
    }

    watchForResponse(previousResponseText, previousTurnCount, previousBodyLength);
  }

  // ─── Find Send Button ──────────────────────────────────────
  async function findSendButton(inputEl) {
    const selectors = [
      'button[data-testid="send-button"]',             // ChatGPT's official send button
      'button[aria-label="Send prompt"]',
      'button[aria-label*="Send"]',
      'button[aria-label*="send"]',
      'form button[type="submit"]',
    ];

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && !el.disabled) return el;
    }

    // Walk up from input to find nearby buttons
    if (inputEl) {
      let container = inputEl;
      for (let i = 0; i < 6; i++) {
        if (!container.parentElement) break;
        container = container.parentElement;
        const btns = container.querySelectorAll('button');
        for (const btn of btns) {
          const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
          const testId = (btn.getAttribute("data-testid") || "").toLowerCase();
          if ((aria.includes("send") || testId.includes("send")) && !btn.disabled) {
            return btn;
          }
        }
      }
    }

    // Last resort: find any enabled button with send-related SVG (arrow icon)
    const allButtons = document.querySelectorAll("button");
    for (const btn of allButtons) {
      const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
      const testId = (btn.getAttribute("data-testid") || "").toLowerCase();
      if ((aria.includes("send") || testId.includes("send")) && !btn.disabled) {
        return btn;
      }
    }

    return null;
  }

  // ─── Simulate Click ───────────────────────────────────────
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
  function waitForLLMComplete(selector, previousResponseText, previousTurnCount, previousBodyLength = 0) {
    return new Promise((resolve) => {
      console.log(`[BNP ChatGPT] Engaging MutationObserver for DOM Idle detection (${previousTurnCount} prior turns, ${previousBodyLength} prior chars)...`);
      const startTime = Date.now();
      const MAX_TIMEOUT = 290000; // 290s
      const IDLE_THRESHOLD = 1500; // 1.5s DOM silence = done
      const MIN_WAIT_MS = 1500;    // Never resolve before 1.5s
      const BODY_GROWTH_THRESHOLD = 30;

      let idleTimer = null;
      let lastTextLength = 0;
      let hasStartedGenerating = false;

      const bodyTextGrew = () => {
        return document.body.innerText.length > previousBodyLength + BODY_GROWTH_THRESHOLD;
      };

      const finishAndResolve = (reason) => {
        if (idleTimer) clearTimeout(idleTimer);
        observer.disconnect();
        console.log(`[BNP ChatGPT] LLM Complete via: ${reason}`);
        
        let responseText = getLatestResponse();
        const currentTurns = document.querySelectorAll('[data-message-author-role="assistant"], [data-testid^="conversation-turn-"]');
        const hasNewTurn = currentTurns.length > previousTurnCount;
        const textGrew = bodyTextGrew();
        
        // Use fuzzy matching instead of exact string comparison
        if (!hasNewTurn && !textGrew && isOldResponse(responseText, previousResponseText)) {
            responseText = "";
        }
        
        const lastAssistant = getLastAssistantTurn();
        const hasImage = lastAssistant && (lastAssistant.querySelector('img') !== null || lastAssistant.querySelector('[class*="image"]') !== null);
        
        if (responseText || hasImage) {
            resolve({ text: responseText, hasImage, lastAssistant });
        } else {
            resolve(null);
        }
      };

      const resetIdleTimer = (idleWait = IDLE_THRESHOLD) => {
        if (idleTimer) clearTimeout(idleTimer);
        if (hasStartedGenerating || document.querySelector('.result-streaming')) {
            idleTimer = setTimeout(() => {
                // Minimum wait floor
                const elapsed = Date.now() - startTime;
                if (elapsed < MIN_WAIT_MS) {
                    console.log(`[BNP ChatGPT] Idle fired but only ${elapsed}ms elapsed (min: ${MIN_WAIT_MS}ms). Resetting...`);
                    resetIdleTimer(idleWait);
                    return;
                }
                
                // Double check if ChatGPT is artificially silent but still technically 'thinking'
                const isThinking = !!document.querySelector('.result-streaming, .result-typing, [class*="typing"], [class*="pulse"]:not(button):not(svg), [class*="spin"]:not(button):not(svg), [class*="loading"]:not(button), [aria-busy="true"]');
                
                if (isThinking) {
                    console.log("[BNP ChatGPT] DOM Silent but UI is actively 'thinking'. Ignoring silence.");
                    resetIdleTimer(idleWait);
                    return;
                }
                
                finishAndResolve("DOM Idle Timeout (" + idleWait + "ms)");
            }, idleWait);
        }
      };

      const observer = new MutationObserver(() => {
        if (Date.now() - startTime > MAX_TIMEOUT) {
            finishAndResolve("Hard Timeout (290s)");
            return;
        }

        // Auto-Click Continue
        const continueBtn = Array.from(document.querySelectorAll('button')).find(b =>
          (b.offsetParent !== null) && ((b.innerText || "").includes("Continue generating") || (b.getAttribute("aria-label") || "").includes("Continue generating"))
        );
        if (continueBtn) {
          console.log("[BNP ChatGPT] Auto-clicking 'Continue generating'...");
          continueBtn.click();
          resetIdleTimer();
          return;
        }

        let currentText = getLatestResponse() || "";
        const currentTurns = document.querySelectorAll('[data-message-author-role="assistant"], [data-testid^="conversation-turn-"]');
        const hasNewTurn = currentTurns.length > previousTurnCount;
        // Use fuzzy matching instead of exact comparison
        if (!hasNewTurn && isOldResponse(currentText, previousResponseText)) {
            currentText = "";
        }

        const lastAssistant = getLastAssistantTurn();
        const hasImage = lastAssistant && (lastAssistant.querySelector('img') !== null || lastAssistant.querySelector('[class*="image"]') !== null);
        const textGrew = bodyTextGrew();

        // Detect new thinking/pulsing animations
        const isThinking = !!document.querySelector('.result-streaming, .result-typing, [class*="typing"], [class*="pulse"]:not(button):not(svg), [class*="spin"]:not(button):not(svg), [class*="loading"]:not(button), [aria-busy="true"]');

        if (!hasStartedGenerating && (currentText || hasImage || textGrew || isThinking)) {
            hasStartedGenerating = true;
            console.log(`[BNP ChatGPT] Detected new generation start! (text: ${!!currentText}, image: ${hasImage}, bodyGrew: ${textGrew}, thinking: ${isThinking})`);
            resetIdleTimer();
        }

        if (hasStartedGenerating) {
            // Guardrail Policy Detection
            const isGuardrail = currentText && (
              currentText.includes("violate our guardrails") || 
              currentText.includes("limitations on content") ||
              currentText.includes("I cannot fulfill this request")
            );
            if (isGuardrail) {
               console.log("🚨 Policy hit. Finishing.");
               finishAndResolve("Guardrail Policy Hit");
               return;
            }

            // The absolute source of truth for ChatGPT generating is the Stop Button or the Thinking Indicator.
            const stopBtn = document.querySelector([
                '[data-testid="stop-button"]', 
                '[aria-label="Stop generating"]', 
                '[aria-label="Stop streaming"]', 
                '[aria-label*="Stop generating"]',
                'button[aria-label="Stop"]'
            ].join(', '));
            
            // Heuristic for the new Stop Square SVG (a button containing a square <rect> with width>=10 or specific paths)
            const stopSvg = document.querySelector('button svg rect[width="10"][height="10"], button svg rect[width="14"][height="14"]');

            // The '...' thinking bubble shown in the screenshot
            const ellipsisBubble = document.querySelector('.result-streaming, .result-typing, [class*="typing-indicator"], div > svg circle:nth-child(3)');

            // Also check for the send button - if it's completely missing, it usually means the stop button took its place
            const sendBtn = document.querySelector('[data-testid="send-button"]');
            
            // We consider it still streaming if the stop button is visible, the stop SVG is found, OR ellipsis is present
            const isStillStreaming = (stopBtn && stopBtn.offsetParent !== null) || 
                                     (stopSvg && stopSvg.closest('button')?.offsetParent !== null) || 
                                     ellipsisBubble || 
                                     isThinking;

            let textChanged = false;
            if (currentText.length !== lastTextLength) {
                lastTextLength = currentText.length;
                textChanged = true;
                if (currentText.trim() && currentRequestId) {
                    sendResponse(currentRequestId, cleanResponseText(currentText), [], "partial");
                }
            }

            if (isStillStreaming) {
                resetIdleTimer(4000); 
            } else {
                // To prevent premature exit (like when the stop button briefly flickers or internet is slow),
                // we ONLY rely on the text stability + IDLE_THRESHOLD when no stop button is visible.
                // We REMOVED the "Copy button" check because ChatGPT now renders it during streaming on hover.
                if (textChanged) {
                    resetIdleTimer(IDLE_THRESHOLD);
                } else {
                    // Let the idle timer finish it. Don't force resolve here.
                }
            }
        }
      });

      const targetNode = document.querySelector("main") || document.body;
      observer.observe(targetNode, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
          attributeFilter: ['disabled', 'class', 'style']
      });

      setTimeout(() => finishAndResolve("Failsafe Hard Timeout (290s)"), MAX_TIMEOUT);
    });
  }

  // ─── Response Flow Execution ────────────────────────────────
  async function watchForResponse(previousResponseText, previousTurnCount = 0, previousBodyLength = 0) {
    const logMsg = (text) => {
      console.log(`[BNP ChatGPT] ${text}`);
      window.dispatchEvent(new CustomEvent("bnp-log", { detail: { source: "ChatGPT", text } }));
      chrome.runtime.sendMessage({ type: "BNP_LOG", source: "ChatGPT", text });
    };

    if (typeof responseObserver !== 'undefined' && responseObserver) {
      responseObserver.disconnect();
      responseObserver = null;
    }

    const payload = await waitForLLMComplete("main", previousResponseText, previousTurnCount, previousBodyLength);
    
    if (!payload) {
        logMsg("Timeout: ChatGPT did not produce a response.");
        sendErrorResponse(currentRequestId, "Timeout: ChatGPT did not produce a response.");
        return;
    }

    const { text: rawFinalText, hasImage, lastAssistant } = payload;
    let finalResult = rawFinalText;

    // 🧠 SMART DETECTION MECHANISM: Wait for Full Render if Image Detected
    if (hasImage && lastAssistant) {
         logMsg("Image sequence detected. Engaging Smart Ready Detection...");
         let imageReady = false;
         let lastImageCount = 0;
         let imageStability = 0;

         for (let i = 0; i < 60; i++) {
            const images = Array.from(lastAssistant.querySelectorAll('img')).filter(img => {
               const style = window.getComputedStyle(img);
               const isDalle = img.src?.includes('oaiusercontent') || img.src?.includes('blob:') || img.src?.includes('dalle');
               // naturalWidth can be 0 initially for blobs; allow offsetWidth as fallback
               return style.opacity > 0.3 && (img.naturalWidth > 100 || img.offsetWidth > 100 || isDalle);
            });

            const finUi = lastAssistant.querySelector('button[aria-label*="Download"], [data-testid*="download"], button[aria-label*="Share"], button[aria-label*="Regenerate"], [aria-label*="Image 1"], [class*="download"], [class*="share"]');
           
           if (images.length > 0 && finUi) {
              if (images.length === lastImageCount) {
                 imageStability++;
              } else {
                 lastImageCount = images.length;
                 imageStability = 0;
              }
              if (imageStability >= 3) { // 1.5s stability
                 logMsg(`Smart Ready: ${images.length} high-res images stabilized.`);
                 imageReady = true;
                 break;
              }
           }
           await delay(500);
         }
         
         if (!imageReady) logMsg("Smart detection timed out; proceeding with best available pixels.");
         else await delay(500);
    } else {
         await delay(500); // Micro-settle for UI
    }

    // Refresh final text and images
    finalResult = cleanResponseText(getLatestResponse() || finalResult || "Image generated.");
    
    // Attempt extra scrape if empty text but no image
    if (!finalResult && !hasImage) {
        logMsg("Warning: Final text is empty.");
    }

    const images = await getLatestImages(logMsg);
    const videos = await getLatestVideos(logMsg);
    const files = await getLatestFiles(logMsg);
    
    sendResponse(currentRequestId, finalResult, images, "finished", videos, files);
  }

  // ─── Get Last Assistant Turn Element ────────────────────────
  function getLastAssistantTurn() {
    // 1. Bottom-up approach: Find the actual markdown renderers first (most indestructible)
    const markdowns = document.querySelectorAll('.markdown, .prose, div[class*="markdown"]');
    if (markdowns.length > 0) {
        let el = markdowns[markdowns.length - 1];
        // Walk up the DOM tree up to main or body
        while (el.parentElement && !el.parentElement.matches('main, body')) {
            if (el.matches('[data-testid^="conversation-turn-"], [data-message-author-role], article, .agent-turn')) {
                return el;
            }
            el = el.parentElement;
        }
        // Fallback: just return the parent of the markdown itself
        return markdowns[markdowns.length - 1].parentElement;
    }

    // 2. Fallback to traditional top-down selectors
    const turns = document.querySelectorAll(
      '[data-message-author-role="assistant"], ' +
      '[data-testid^="conversation-turn-"], ' +
      '.group\\/conversation-turn, ' +
      '.agent-turn, ' +
      'article'
    );
    if (turns.length === 0) return null;
    return turns[turns.length - 1];
  }

  // ─── Extract Latest Response ────────────────────────────────
  function getLatestResponse() {
    // ChatGPT renders assistant responses in specific containers
    const selectors = [
      '.markdown',
      '.prose',
      'div[class*="markdown"]',
      'div[class*="prose"]',
    ];

    let responseElements = [];

    const lastTurn = getLastAssistantTurn();
    if (!lastTurn) return null;

    for (const sel of selectors) {
      const els = lastTurn.querySelectorAll(sel);
      if (els.length > 0) {
        responseElements = Array.from(els).filter(el => {
          // If the element itself is a citation container, skip it
          if (el.classList.contains('citations-dropdown') || el.classList.contains('citation')) return false;
          if (el.getAttribute('aria-label') === 'Citation') return false;
          
          // Return true even if empty so we don't accidentally get the previous turn
          return true;
        });
        if (responseElements.length > 0) break;
      }
    }

    if (responseElements.length === 0) {
        const turnText = (lastTurn.innerText || lastTurn.textContent || "").trim();
        if (turnText.length > 0) return cleanResponseText(turnText);
    }

    if (responseElements.length === 0) return null;

    // Process ALL response elements to preserve full structural integrity
    const blockTexts = responseElements.map(el => {
        // Create a temporary clone to prune technical UI nodes
        const clone = el.cloneNode(true);
        
        // CRITICAL: Convert <hr> tags into literal "---" before extraction
        // innerText often ignores <hr> or fails to add a newline
        clone.querySelectorAll('hr').forEach(hr => {
            const marker = document.createTextNode('\n---\n');
            hr.parentNode.replaceChild(marker, hr);
        });

        // Recover block-level line breaks because unattached nodes lose innerText formatting
        clone.querySelectorAll('br').forEach(node => {
            node.parentNode.replaceChild(document.createTextNode('\n'), node);
        });
        clone.querySelectorAll('p, div').forEach(node => {
            node.appendChild(document.createTextNode('\n\n'));
        });
        clone.querySelectorAll('li').forEach(node => {
            const marker = document.createTextNode('- ' + node.textContent + '\n');
            node.parentNode.replaceChild(marker, node);
        });

        // Prune other technical UI nodes (Citations, Buttons, Icons, and Image Controls)
        clone.querySelectorAll('[aria-label="Citation"], [role="button"], button, svg, [class*="citation"], [class*="ImageAction"], [class*="Download"], [class*="Share"]').forEach(node => node.remove());
        
        // Extract text and ensure preserved newlines
        return (clone.textContent || "").replace(/\n{3,}/g, '\n\n').trim();
    });

    // Join blocks with a SINGLE newline - innerText already handles paragraph breaks.
    // Double newlines here cause "Double-Spaced" looks in Messenger.
    const joinedText = blockTexts.filter(t => t.length > 0).join('\n');
    
    // Post-processing: Remove "Copy code" strings that ChatGPT injects near the bottom-right of blocks
    const finalClean = joinedText
        .replace(/\bCopy\s+code\b/gi, '')
        .replace(/^\s*Copy\s*$/gm, '')
        .trim();

    return cleanResponseText(finalClean || null);
  }

  // ─── Old Response Matching ──────────────────────────────────
  function isOldResponse(newText, oldText) {
    if (!oldText) return false;
    const cleanNew = newText.trim().replace(/\s+/g, ' ');
    const cleanOld = oldText.trim().replace(/\s+/g, ' ');

    if (cleanNew === cleanOld) return true;
    if (cleanNew.startsWith(cleanOld) && cleanNew.length < cleanOld.length + 20) return true;
    return false;
  }

  // ─── Clean Response Text ────────────────────────────────────
  function cleanResponseText(text) {
    if (!text) return "";
    let cleaned = text;

    // Remove BNP protocol headers (Updated for V4 KNOWLEDGE BASE)
    cleaned = cleaned.replace(/\[SYSTEM OVERRIDE ACTIVE:[\s\S]*?\]\n/gi, "");
    cleaned = cleaned.replace(/CRITICAL: You are connected to the BANE Chrome Extension Bridge[\s\S]*?\n/gi, "");
    cleaned = cleaned.replace(/REQUIREMENT: Follow all rules in BANE_NLP_BRAIN_knowledge\.md exactly\.\n/gi, "");
    cleaned = cleaned.replace(/\[CONTEXT: [\s\S]*?\]\n/gi, "");
    cleaned = cleaned.replace(/\[KNOWLEDGE BASE\][\s\S]*?\[USER_ID: \d+\]\s*USER:.*?\n/gi, "");
    cleaned = cleaned.replace(/\[MANDATORY RULES\] MANDATORY_RULES\.txt[\s\S]*?\[USER_ID: \d+\]\s*USER:.*?\n/gi, "");
    cleaned = cleaned.replace(/\[KNOWLEDGE BASE\] Docs\/InjectionHeaderContext\/BANE_NLP_BRAIN_knowledge\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[CHROME_PROFILE_SYSTEM\] Docs\/InjectionHeaderContext\/BANE_CHROME_PROFILE_SYSTEM\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[SAVE_PATHS\][\s\S]*?Screenshot -> [^\n]*\n/gi, "");
    cleaned = cleaned.replace(/\[MANDATORY RULES\] MANDATORY_RULES\.txt\s*/gi, "");
    cleaned = cleaned.replace(/\[WORKSPACE MAP\] WORKSPACE_ARCHITECTURE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[PROJECT CONTEXT\] ACTIVE_PROJECTS_CONTEXT\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[SCENARIOS GUIDE\] BANE_SCENARIOS\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[DEPLOYMENT_GUIDE\] AUTONOMOUS_DEPLOYMENT_GUIDE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[MCP_TOOL_GUIDE\] MCP_TOOLS_DOCUMENTATION\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[EXECUTION COMMAND\]\s*/gi, "");
    cleaned = cleaned.replace(/\[PLATFORM: [\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[USER_ID: [\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/USER QUERY:\s*/gi, "");
    cleaned = cleaned.replace(/USER:\s*/gi, "");

    // Remove ChatGPT UI artifacts
    cleaned = cleaned.replace(/^(ChatGPT said|ChatGPT|You said)/gmi, "");
    cleaned = cleaned.replace(/\bCopy code\b/gi, "");
    cleaned = cleaned.replace(/^\s*(Copy|Edit|Share|Download|Regenerate)\s*$/gmi, "");
    cleaned = cleaned.replace(/\s(Copy|Edit|Share|Download|Regenerate)$/gmi, "");

    // Remove citation artifacts and file references
    cleaned = cleaned.replace(/\[cite_start\]/gi, "");
    cleaned = cleaned.replace(/\[cite_end\]/gi, "");
    cleaned = cleaned.replace(/\[cite:\s*[\d,\s]+\]/gi, "");
    cleaned = cleaned.replace(/\[\d+(?:\s*,\s*\d+)*\]/g, "");
    cleaned = cleaned.replace(/:contentReference\[oaicite:\d+\]\{index=\d+\}/gi, "");
    cleaned = cleaned.replace(/\{index=\d+\}/gi, "");
    cleaned = cleaned.replace(/\[oaicite:\d+\]/gi, "");
    
    // Nuclear UUID & Blocky-HEX cleanup (handles full, partial, and truncated with all dot styles)
    // Matches patterns like d262f071-c00f-407d-bb37-5f9bb82... or d262f071...
    cleaned = cleaned.replace(/[a-f0-9\-]{8,}(\.{1,}|…)/gi, "");
    cleaned = cleaned.replace(/[a-f0-9]{8,}(\.{1,}|…)/gi, "");
    cleaned = cleaned.replace(/[a-f0-9]{8}-[a-f0-9\-]+/gi, "");
    cleaned = cleaned.replace(/\s[a-f0-9]{8,}\s/gi, " ");
    
    // Remove standalone citation "Sources" label
    cleaned = cleaned.replace(/^\s*Sources\s*$/gmi, "");
    cleaned = cleaned.replace(/\bSources\b/gi, "");
    cleaned = cleaned.replace(/Sources\s*/g, "");
    
    // 🔥 Nuclear Cleanup: Remove the accidental HTML artifacts created by the previous scraper version
    cleaned = cleaned.replace(/<b>(.*?)<\/b>/gi, "$1");
    cleaned = cleaned.replace(/<i>(.*?)<\/i>/gi, "$1");

    // ⚡ SURGICAL SPACING: Collapse excessive vertical sprawl
    // 1. Remove trailing spaces on lines that cause weird wrapping
    cleaned = cleaned.split('\n').map(line => line.trimEnd()).join('\n');
    // 2. Collapse 3+ newlines into exactly 2 (for clean section gaps)
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
    // 3. Remove leading space on lines - Removed to preserve python indentation

    // Clean excessive horizontal whitespace - Removed to preserve python indentation
    cleaned = cleaned.trim();

    // Reject obvious placeholder text
    const isSuspicious =
      /^(loading|thinking|generating|creating|working)\.{0,3}$/i.test(cleaned) &&
      cleaned.length < 30;

    if (isSuspicious) return "";

    return cleaned.trim();
  }

  // ─── Send Response Back ─────────────────────────────────────
  function sendResponse(requestId, text, images = [], status = "finished", videos = [], files = []) {
    const responsePayload = {
      pipeline: PIPELINE_NAME,
      id: requestId,
      type: "response",
      source: "chatgpt",
      status: status,
      timestamp: new Date().toISOString(),
      payload: {
        text: text,
        images: images,
        videos: videos,
        files: files
      },
    };

    window.dispatchEvent(
      new CustomEvent("bnp-response", { detail: responsePayload })
    );

    if (status === "finished") {
      isProcessingPrompt = false;
      setTimeout(processNextPrompt, 500);
    }
  }

  function sendErrorResponse(requestId, errorMessage) {
    sendResponse(requestId, `[BNP Error] ${errorMessage}`);
  }

  // ─── Utility Functions ──────────────────────────────────────
  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  let sentImageUrls = new Set(); // Global tracker to prevent recycling old images

  // ─── Extract Latest Images ──────────────────────────────────
  async function getLatestImages(logMsg) {
    if (logMsg) logMsg("Searching for latest AI images...");
    const candidates = [];
    const startTime = Date.now();

    while (Date.now() - startTime < 12000) { // Keep trying for 12s
      const lastTurn = getLastAssistantTurn();
      if (!lastTurn) {
        if (logMsg) logMsg("No assistant turn found for image scan.");
        await delay(1000);
        continue;
      }

      // Broad image search
      const turnImgs = Array.from(lastTurn.querySelectorAll('img, [class*="Dalle"], [class*="image"], [class*="visual"]'));
      
      if (turnImgs.length > 0) {
        for (const imgEl of turnImgs) {
          let src = (imgEl.tagName === 'IMG') ? imgEl.src : (imgEl.style?.backgroundImage || "");
          if (src && src.includes('url("')) {
              src = src.split('url("')[1].split('")')[0];
          }

          if (src && !sentImageUrls.has(src)) {
            const { valid, area } = isValidForResult(imgEl, logMsg);
            if (valid) {
              candidates.push({ el: imgEl, src, area });
            }
          }
        }
      }

      if (candidates.length > 0) break;
      await delay(1500);
    }

    if (candidates.length === 0) return [];

    // Prioritize the LARGEST image (highest resolution)
    // This avoids capturing thumbnails or small avatar icons that class-matched.
    candidates.sort((a, b) => b.area - a.area);
    
    // We only want the best image(s) from this turn
    const bestCandidate = candidates[0];
    if (logMsg) logMsg(`Capturing best pixels: ${bestCandidate.src.substring(0, 40)}... (Area: ${bestCandidate.area})`);
    
    const dataUrl = await imageToDataURL(bestCandidate.el, logMsg);
    if (dataUrl) {
      sentImageUrls.add(bestCandidate.src);
      return [dataUrl];
    }
    
    return [];
  }

  const sentVideoUrls = new Set();
  async function getLatestVideos(logMsg) {
    const lastTurn = getLastAssistantTurn();
    if (!lastTurn) return [];

    const videoElements = Array.from(lastTurn.querySelectorAll('video, source'));
    const results = [];

    for (const vid of videoElements) {
       const src = vid.src || vid.getAttribute('src');
       if (!src || sentVideoUrls.has(src)) continue;
       
       if (vid.closest('[data-message-author-role="assistant"]')) {
          if (logMsg) logMsg(`Detected new video asset: ${src.substring(0, 40)}...`);
          sentVideoUrls.add(src);
          results.push(src);
       }
    }
    return results;
  }

  const sentFileUrls = new Set();
  async function getLatestFiles(logMsg) {
    const lastTurn = getLastAssistantTurn();
    if (!lastTurn) return [];

    // Search for download links or elements that look like file downloads
    // ChatGPT often uses <a> tags with download attributes or specific classes for file icons
    const fileLinks = Array.from(lastTurn.querySelectorAll('a[download], a[href*="oaiusercontent.com/file-"], [class*="download-link"], [data-testid*="file-download"]'));
    const results = [];

    for (const link of fileLinks) {
       let src = link.href || link.getAttribute('href');
       let name = link.getAttribute('download') || link.textContent || "document";
       
       if (!src || sentFileUrls.has(src)) continue;
       
       // Sometime href is relative - make it absolute
       if (src.startsWith('/')) {
         src = window.location.origin + src;
       }

       if (logMsg) logMsg(`Detected generated document: ${name} (${src.substring(0, 30)}...)`);
       
       // Fetch as DataURL (Base64) so we can send it through the websocket
       // Reuse the imageToDataURL logic but for general files
       const dataUrl = await imageToDataURL({ src: src }, logMsg); 
       if (dataUrl) {
          sentFileUrls.add(src);
          results.push({ name: name, data: dataUrl });
       }
    }
    return results;
  }

  function isValidForResult(imgEl, logMsg) {
    let src = imgEl.src;
    if (!src && imgEl.style?.backgroundImage) {
        src = imgEl.style.backgroundImage.split('url("')[1]?.split('")')[0];
    }
    if (!src || src.includes('avatar') || src.includes('profile')) return { valid: false, area: 0 };

    // Reject user attached images
    if (imgEl.closest('file-attachment, [data-message-author-role="user"]')) {
      return { valid: false, area: 0 };
    }

    const w = imgEl.naturalWidth || imgEl.width || imgEl.offsetWidth || 0;
    const h = imgEl.naturalHeight || imgEl.height || imgEl.offsetHeight || 0;
    const area = w * h;
    const isBig = (w >= 100 || h >= 100);

    // Reject images that are largely transparent or still hidden/fading in
    const style = window.getComputedStyle(imgEl);
    if (style.opacity < 0.5 || style.visibility === 'hidden') return { valid: false, area: 0 };

    const isGeneratedSrc = src.startsWith('blob:') ||
      src.includes('oaiusercontent') ||
      src.includes('webp') ||
      src.includes('dalle') ||
      src.includes('openai') ||
      src.includes('bing') ||
      src.includes('canary');

    const valid = (area > 5000 || isGeneratedSrc) && !src.startsWith('data:image/svg');
    if (valid && logMsg && area > 50000) {
        logMsg(`Validated pixels: ${w}x${h} | Domain: ${src.includes('blob:') ? 'blob' : 'cdn'} | Src: ${src.substring(0, 30)}...`);
    }
    return { valid, area };
  }

  async function imageToDataURL(imgElement, logMsg) {
    let url = imgElement.src;
    if (!url && imgElement.style?.backgroundImage) {
        url = imgElement.style.backgroundImage.split('url("')[1]?.split('")')[0];
    }
    if (!url || url.startsWith('data:image/svg')) return null;

    if (url.startsWith('data:image/')) {
      if (logMsg) logMsg(`Image already Base64 (${url.length} chars)`);
      return url;
    }

    if (logMsg) logMsg(`Capturing Binary Data for: ${url.substring(0, 40)}...`);

    // Strategy A: BACKGROUND DOWNLOAD API (Nuclear Option)
    try {
      if (logMsg) logMsg(`Trying Chrome Downloads API fetch...`);
      const mainWorldResponse = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Timeout")), 20000);
        chrome.runtime.sendMessage({ type: "BNP_FETCH_IMAGE_MAIN_WORLD", url: url }, (resp) => {
          clearTimeout(timeout);
          resolve(resp);
        });
      });
      if (mainWorldResponse && mainWorldResponse.dataUrl) {
        if (logMsg) logMsg(`Downloads API fetch Success! (${mainWorldResponse.dataUrl.length} chars)`);
        return mainWorldResponse.dataUrl;
      }
    } catch (e) { }

    // Strategy B: Background service worker fetch
    try {
      if (logMsg) logMsg(`Trying background fetch...`);
      const bgResponse = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Timeout")), 15000);
        chrome.runtime.sendMessage({ type: "BNP_FETCH_IMAGE", url: url }, (resp) => {
          clearTimeout(timeout);
          resolve(resp);
        });
      });
      if (bgResponse && bgResponse.dataUrl) {
        if (logMsg) logMsg(`Background fetch Success! (${bgResponse.dataUrl.length} chars)`);
        return bgResponse.dataUrl;
      }
    } catch (e) { }

    // Fallback: Canvas
    try {
      if (logMsg) logMsg(`Trying Canvas fallback...`);
      return await new Promise((resolve) => {
        const canvas = document.createElement('canvas');
        canvas.width = imgElement.naturalWidth || imgElement.width;
        canvas.height = imgElement.naturalHeight || imgElement.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(imgElement, 0, 0);
        const dataUrl = canvas.toDataURL("image/webp", 0.9);
        resolve(dataUrl);
      });
    } catch (e) {
      if (logMsg) logMsg(`Canvas fallback failed: ${e.message}`);
    }

    return null;
  }

  console.log("[BNP ChatGPT] Content script ready");
})();
