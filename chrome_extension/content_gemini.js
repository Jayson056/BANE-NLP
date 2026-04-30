/**
 * BNP Content Script — Gemini
 * ============================
 * Handles prompt injection and response capture on gemini.google.com.
 *
 * Strategy:
 *   1. Listen for "bnp-prompt" events from the WebSocket bridge
 *   2. Find Gemini's input area and inject the prompt text
 *   3. Trigger the send action
 *   4. Observe the DOM for the AI response
 *   5. Dispatch a "bnp-response" event with the response text
 */

(function () {
  "use strict";

  const PIPELINE_NAME = "BNP";
  // How often to check for completed responses
  const POLL_INTERVAL_MS = 50;
  const RESPONSE_TIMEOUT_MS = 290000; // slightly less than Python timeout (300s)

  let currentRequestId = null;
  let responseObserver = null;
  let capturedClipboardText = null;

  // ─── Global Utilities ──────────────────────────────────────
  const logMsg = (text) => {
    console.log(`[BNP Gemini] ${text}`);
    window.dispatchEvent(new CustomEvent("bnp-log", { detail: { source: "Gemini", text } }));
    chrome.runtime.sendMessage({ type: "BNP_LOG", source: "Gemini", text });
  };

  const logEvent = (level, text) => {
    logMsg(`[${level}] ${text}`);
  };

  let sentImageFingerprints = new Set(); 

  function getImageFingerprint(img) {
    try {
      if (!img.src || !img.complete || img.naturalWidth === 0) return null;
      const canvas = document.createElement('canvas');
      canvas.width = 16;
      canvas.height = 16;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, 16, 16);
      const data = ctx.getImageData(0, 0, 16, 16).data;
      let hash = 0;
      for (let i = 0; i < data.length; i += 4) {
        hash = ((hash << 5) - hash + data[i] + data[i + 1] + data[i + 2]) | 0;
      }
      return 'fp_' + hash.toString(36);
    } catch (e) {
      return img.src ? 'url_' + img.src : null;
    }
  }

  // ─── Notify Background ──────────────────────────────────────
  chrome.runtime.sendMessage({
    type: "BNP_CONTENT_READY",
    target: "gemini",
  });

  console.log("[BNP Gemini] Content script loaded. Bootstrapping Interceptors...");

  // ─── Clipboard Interceptor (Main World Injection) ──────────
  // Gemini mostly uses navigator.clipboard.writeText when you click the copy button.
  // We override it in the main world so we can intercept the RAW markdown.
  const bootstrapScript = document.createElement('script');
  bootstrapScript.textContent = `
    (function() {
      const origWriteText = navigator.clipboard.writeText;
      navigator.clipboard.writeText = async function(text) {
        window.postMessage({ type: 'BNP_CLIPBOARD_OVERRIDE', text: text }, '*');
        return origWriteText.apply(this, arguments);
      };

      const origWrite = navigator.clipboard.write;
      navigator.clipboard.write = async function(data) {
        if (data && data.length > 0) {
          try {
            for (const item of data) {
              if (item.types && item.types.includes('text/plain')) {
                const blob = await item.getType('text/plain');
                const text = await blob.text();
                window.postMessage({ type: 'BNP_CLIPBOARD_OVERRIDE', text: text }, '*');
                break;
              }
            }
          } catch(e) {}
        }
        return origWrite ? origWrite.apply(this, arguments) : Promise.resolve();
      };
      
      // Also catch standard execCommand copy just in case
      document.addEventListener('copy', (e) => {
         const text = window.getSelection().toString();
         if (text) window.postMessage({ type: 'BNP_CLIPBOARD_OVERRIDE', text: text }, '*');
      }, true);
    })();
  `;
  document.documentElement.appendChild(bootstrapScript);
  bootstrapScript.remove();

  // Listen for the broadcast from the main world injection
  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'BNP_CLIPBOARD_OVERRIDE') {
      capturedClipboardText = event.data.text;
    }
  });

  // ─── Request Queue to Prevent Overlaps ────────────────────────
  const promptQueue = [];
  const processedRequestIds = new Set();
  let isProcessingPrompt = false;

  window.addEventListener("bnp-prompt", (event) => {
    const data = event.detail;
    if (!data.id) return;

    // De-duplicate: If we've already queued or processed this exact ID, ignore it.
    if (processedRequestIds.has(data.id)) {
      console.log(`[BNP Gemini] Ignoring duplicate prompt ID: ${data.id}`);
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
      console.log("[BNP Gemini] Signal: Starting new conversation...");
      // Redirecting to root is the cleanest way to clear context for a new chat
      window.location.href = "https://gemini.google.com/";
    } else if (action === "navigate") {
      const url = event.detail?.url;
      if (url) {
        console.log("[BNP Gemini] Signal: Navigating to", url);
        window.location.href = url;
      }
    }
  });

  async function processNextPrompt() {
    if (isProcessingPrompt || promptQueue.length === 0) return;
    isProcessingPrompt = true;

    const data = promptQueue.shift();

    if (data.target !== "gemini") {
      console.log("[BNP Gemini] Ignoring prompt for different target:", data.target);
      isProcessingPrompt = false;
      processNextPrompt();
      return;
    }

    const message = data.payload?.message;
    if (!message) {
      console.error("[BNP Gemini] No message in payload");
      isProcessingPrompt = false;
      processNextPrompt();
      return;
    }

    currentRequestId = data.id;
    console.log(`[BNP Gemini] Processing prompt (${currentRequestId}):`, message.substring(0, 80));

    // --- PRE-SEED IMAGE TRACKER ---
    // If we just refreshed or started a new request, we MUST ignore all images 
    // that already exist on the screen to prevent hallucinating old images!
    // NOTE: We use canvas-based content fingerprinting instead of URL matching
    // because Gemini regenerates blob: URLs on every re-render, making URL
    // tracking useless for deduplication.
    const existingImages = document.querySelectorAll('img');
    let preSeedCount = 0;
    existingImages.forEach(img => {
      if (img.src) {
        const fp = getImageFingerprint(img);
        if (fp) {
          sentImageFingerprints.add(fp);
          preSeedCount++;
        }
      }
    });
    if (preSeedCount > 0) logMsg(`Pre-seeded image tracker with ${preSeedCount} existing images to prevent leakages.`);

    try {
      // --- MULTI-FILE INJECTION ---
      const files = data.payload?.files || (data.payload?.file ? [data.payload.file] : []);

      // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      // SPEED-OPTIMIZED DELAY CONSTANTS (Content-Type Aware)
      // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      const DELAY_TEXT_ONLY_MS = 2000;   // Normal text: 3s
      const DELAY_IMAGE_ATTACH_MS = 25000;  // Image attachments: 30s max
      const DELAY_OGG_VOICE_MS = 38000;  // OGG voice messages: 43s max
      const DELAY_GENERIC_MEDIA_MS = 25000;  // Other media fallback: 30s max

      // Chip selector for the INPUT area only (not the chat history)
      const CHIP_SELECTOR = 'file-attachment-chip, gallery-item, mat-chip, .file-chip, .attachment-item, [aria-label*="Attachment"], .uploaded-file';

      // Helper: count current file chips in the input area
      const countInputChips = () => {
        return document.querySelectorAll(CHIP_SELECTOR).length;
      };

      // Determine the MAX wait ceiling based on file MIME types
      let contentTypeMaxWait = DELAY_TEXT_ONLY_MS;
      if (files.length > 0) {
        for (const file of files) {
          const mime = (file.mime || "").toLowerCase();
          const fname = (file.name || "").toLowerCase();
          if (mime === "audio/ogg" || mime === "audio/opus" || fname.endsWith(".ogg") || fname.endsWith(".opus") || fname.endsWith(".oga")) {
            contentTypeMaxWait = Math.max(contentTypeMaxWait, DELAY_OGG_VOICE_MS);
          } else if (mime.startsWith("audio/") || mime.startsWith("video/")) {
            contentTypeMaxWait = Math.max(contentTypeMaxWait, DELAY_GENERIC_MEDIA_MS);
          } else if (mime.startsWith("image/")) {
            contentTypeMaxWait = Math.max(contentTypeMaxWait, DELAY_IMAGE_ATTACH_MS);
          } else {
            // Documents, PDFs, etc.
            contentTypeMaxWait = Math.max(contentTypeMaxWait, DELAY_IMAGE_ATTACH_MS);
          }
        }
        logMsg(`[SPEED] Content-aware max wait ceiling: ${contentTypeMaxWait / 1000}s for ${files.length} file(s)`);
      } else {
        logMsg(`[SPEED] Text-only message. Injecting fast (${DELAY_TEXT_ONLY_MS / 1000}s ceiling).`);
      }

      for (const file of files) {
        // Count chips BEFORE injection so we can detect NEW ones
        const chipCountBefore = countInputChips();

        logMsg(`Injecting file: ${file.name}... (${chipCountBefore} chips before)`);
        await injectFile(file);

        // REALTIME SYNC: Wait for file to be FULLY uploaded before next action
        logMsg(`Waiting for upload of ${file.name} to complete...`);
        let attachmentReady = false;

        // Detect content type for THIS specific file
        const mime = (file.mime || "").toLowerCase();
        const fname = (file.name || "").toLowerCase();
        const isOggVoice = mime === "audio/ogg" || mime === "audio/opus" || fname.endsWith(".ogg") || fname.endsWith(".opus");
        const isMediaFile = mime.startsWith("audio/") || mime.startsWith("video/");
        const isImageFile = mime.startsWith("image/");
        const needsExtendedWait = isMediaFile || (file.data && file.data.length > 500000);

        // SPEED: Use tight per-file max waits based on MIME
        let fileMaxWaitMs;
        if (isOggVoice) {
          fileMaxWaitMs = DELAY_OGG_VOICE_MS;
        } else if (isImageFile) {
          fileMaxWaitMs = DELAY_IMAGE_ATTACH_MS;
        } else if (isMediaFile) {
          fileMaxWaitMs = DELAY_GENERIC_MEDIA_MS;
        } else {
          fileMaxWaitMs = DELAY_IMAGE_ATTACH_MS;
        }

        // Chip detection: fast polling, tight timeouts
        const chipDetectDelay = 150;  // SPEED: was 300ms, now 150ms
        const chipDetectAttempts = Math.floor(Math.min(fileMaxWaitMs, 15000) / chipDetectDelay);

        // SPEED: Realtime sync polling (50ms)
        const fastPollInterval = 50;  // SPEED: was 100ms, now 50ms
        const maxPollAttempts = Math.floor(fileMaxWaitMs / fastPollInterval);
        const requiredStableTicks = needsExtendedWait ? 6 : 3; // SPEED: was 8/4, now 6/3

        logMsg(`[SPEED] File: ${file.name} | Type: ${isOggVoice ? 'OGG Voice' : isImageFile ? 'Image' : isMediaFile ? 'Media' : 'Document'} | Max wait: ${fileMaxWaitMs / 1000}s`);

        // Wait for a NEW chip to appear (chip count must INCREASE)
        let fileChip = null;
        for (let i = 0; i < chipDetectAttempts; i++) {
          const currentCount = countInputChips();
          if (currentCount > chipCountBefore) {
            const allChips = document.querySelectorAll(CHIP_SELECTOR);
            fileChip = allChips[allChips.length - 1];
            logMsg(`[Layer 0] DOM Insertion detected for ${file.name}`);
            break;
          }
          await delay(chipDetectDelay);
        }

        if (!fileChip) {
          const allChips = document.querySelectorAll(CHIP_SELECTOR);
          if (allChips.length > 0) fileChip = allChips[allChips.length - 1];
        }

        if (fileChip) {
          let stableCount = 0;

          for (let i = 0; i < maxPollAttempts; i++) {
            await delay(fastPollInterval);

            // --- LAYER 1: Visual Spinner Detection ---
            const hasSpinner = fileChip.querySelector('mat-spinner, [role="progressbar"], svg circle[state="uploading"]') !== null;
            const layer1Passed = !hasSpinner;

            // --- LAYER 2: Semantic HTML Text Status ---
            const chipHTML = fileChip.innerHTML.toLowerCase();
            const textContent = fileChip.innerText.toLowerCase();
            const isTextUploading = chipHTML.includes("upload") || chipHTML.includes("progress") || textContent.includes("loading");
            const layer2Passed = !isTextUploading;

            // --- LAYER 3: Error Detection ---
            const hasError = fileChip.querySelector('.error, .failed, [aria-label*="error"]') !== null || textContent.includes("removed") || textContent.includes("failed") || textContent.includes("try again");

            if (hasError) {
              logMsg(`[FATAL] Upload error detected for ${file.name}!`);
              break;
            }

            const layer3Passed = !hasError;

            if (layer1Passed && layer2Passed && layer3Passed) {
              stableCount++;
            } else {
              stableCount = 0;
            }

            if (stableCount >= requiredStableTicks) {
              attachmentReady = true;
              logMsg(`[REALTIME-SYNC] Upload verified for ${file.name} (${((i + 1) * fastPollInterval) / 1000}s)`);
              break;
            }

            // Progress logging every ~3s for long operations
            if (needsExtendedWait && i > 0 && i % 38 === 0) {
              logMsg(`... Verifying ${file.name} [${(i * fastPollInterval) / 1000}s | L1:${layer1Passed} L2:${layer2Passed} L3:${layer3Passed}]`);
            }
          }
        }
        if (!attachmentReady) logMsg(`[WARNING] Upload verification timeout for ${file.name}`);
      }

      await injectPrompt(message);

    } catch (err) {
      console.error("[BNP Gemini] Injection failed:", err);
      sendErrorResponse(currentRequestId, `Injection failed: ${err.message}`);
    } finally {
      // Guarantee the queue is never permanently locked, even on unexpected errors.
      // sendResponse("finished") already resets this flag on success, but if
      // watchForResponse or injectPrompt throw without calling sendResponse,
      // this safety net prevents a permanent deadlock.
      isProcessingPrompt = false;
      setTimeout(processNextPrompt, 200);
    }
  }


  // ─── File Injection ─────────────────────────────────────────
  async function injectFile(fileData) {
    const { data: base64Data, name, mime } = fileData;

    // 1. Convert Base64 to Blob
    const byteCharacters = atob(base64Data);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: mime });
    const file = new File([blob], name, { type: mime });

    // 2. Find and FORCE focus input area
    let inputEl = await findInputArea();
    if (!inputEl) return;

    // Simplified focus + small text injection to 'awaken' the input
    inputEl.focus();
    inputEl.click?.();
    await delay(25); // SPEED: was 200ms

    // Simulate a tiny input to trigger framework observers
    const keyEvent = new KeyboardEvent('keydown', { key: ' ', bubbles: true });
    inputEl.dispatchEvent(keyEvent);
    await delay(25); // SPEED: was 100ms

    // 3. Simulate Paste event with file
    const dt = new DataTransfer();
    dt.items.add(file);

    const pasteEvent = new ClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true
    });

    inputEl.dispatchEvent(pasteEvent);
    console.log(`[BNP Gemini] File '${name}' pasted into input`);

    // 4. Quick confirmation: Verify file chip appeared (caller does the full wait)
    for (let i = 0; i < 6; i++) {
      const hasFileChip = document.querySelector('mat-chip, .file-chip, .attachment-item, [aria-label*="Attachment"], .uploaded-file, .upload-progress');
      if (hasFileChip) {
        console.log(`[BNP Gemini] Visual Confirm: File '${name}' detected in UI.`);
        break;
      }
      await delay(50); // SPEED: was 300ms
    }
  }

  async function findInputArea() {
    let inputEl = null;
    for (let i = 0; i < 10; i++) {
      const editables = document.querySelectorAll('[contenteditable="true"], [contenteditable="plaintext-only"], textarea, div[role="textbox"]');
      for (const el of editables) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 10) {
          inputEl = el;
          break;
        }
      }
      if (inputEl) break;
      await delay(100);
    }
    return inputEl;
  }

  // ─── Prompt Injection ───────────────────────────────────────
  async function injectPrompt(text) {
    let inputEl = null;

    // Aggressively scan the DOM multiple times to find the input box
    for (let i = 0; i < 20; i++) {
      // Find all contenteditable elements or textareas
      const editables = document.querySelectorAll('[contenteditable="true"], [contenteditable="plaintext-only"], textarea, div[role="textbox"]');

      // We want the most visible/relevant one (often at the bottom, or just the largest)
      for (const el of editables) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 50 && rect.height > 10) {
          inputEl = el;
          break;
        }
      }

      if (inputEl) break;
      await delay(100); // SPEED: was 500ms
    }

    if (!inputEl) {
      sendErrorResponse(currentRequestId, "Fatal: Could not find any input text box on the screen. Please ensure the page is loaded.");
      return;
    }

    // Force focus heavily
    inputEl.focus();
    inputEl.click?.();
    await delay(25); // SPEED: was 100ms

    // Clear existing content safely
    if (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT") {
      inputEl.value = "";
    } else {
      inputEl.innerHTML = "";
    }
    
    // ─── ROBUST LINE-BY-LINE DOM INJECTION ───
    // Modern rich-text editors (ProseMirror/Lexical) truncate bulk insertText at the first newline.
    // We must inject the text line by line to guarantee formatting and full payload delivery.
    const expectedLen = text.length;
    let currentText = "";

    // Strategy 1: Simulated Paste Event (Fastest, cleanest if supported)
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    inputEl.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    await delay(50);
    
    currentText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();

    // Strategy 2: Line-by-Line execCommand Injection (Bulletproof Fallback)
    if (currentText.length < expectedLen * 0.8) {
      console.log("[BNP Gemini] Paste truncated/failed. Falling back to line-by-line execCommand injection...");
      
      // Clear whatever was partially injected
      if (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT") inputEl.value = "";
      else inputEl.innerHTML = "";
      await delay(25);

      const lines = text.split('\n');
      for (let i = 0; i < lines.length; i++) {
        // Inject the text portion
        if (lines[i].length > 0) {
          document.execCommand("insertText", false, lines[i]);
        }
        
        // Inject the line break
        if (i < lines.length - 1) {
          // Dispatch a Shift+Enter keydown to trigger framework line-break logic
          inputEl.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true, cancelable: true }));
          // Fallback native commands if event is ignored
          if (!document.execCommand("insertLineBreak")) {
            document.execCommand("insertText", false, '\n');
          }
        }
      }
    }

    // Strategy 3: Absolute Bruteforce Property Mutation
    await delay(50);
    currentText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
    if (currentText.length < expectedLen * 0.8) {
      console.log("[BNP Gemini] execCommand failed. Using bruteforce property mutation...");
      if (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT") {
        inputEl.value = text;
      } else {
        inputEl.innerText = text;
      }
    }

    // Tell Angular/UI frameworks we modified the text
    const events = ["input", "change", "keydown", "keyup"];
    events.forEach(type => {
      // It's important to mark simulated events for some frameworks
      const ev = new Event(type, { bubbles: true, cancelable: true });
      ev.simulated = true;
      inputEl.dispatchEvent(ev);
    });

    // Wait for the text to actually render in the DOM before we click send.
    // This fixes the issue where the send button clicks too fast, leaving text behind.
    for (let i = 0; i < 10; i++) {
      const currentText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
      if (currentText.length > 0) {
        break;
      }
      await delay(25); // SPEED: was 100ms
    }
    await delay(50); // SPEED: was 300ms — final framework sync

    // Look at the last response BEFORE we send, so we don't accidentally capture it instead of the new one
    const previousResponseText = getLatestResponse();
    // Track model turn count BEFORE sending — used to detect genuinely NEW responses
    // regardless of text content (fixes false "old response" detection for identical replies)
    const previousTurnCount = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"]').length;
    console.log(`[BNP Gemini] Prompt injected and rendered (${previousTurnCount} existing turns), looking for send button...`);

    // Find and click the send button aggressively
    let sendBtn = await findSendButton(inputEl);
    if (sendBtn) {
      // Small delay to let the force-enable settle before clicking
      await delay(25);
      simulateClick(sendBtn);
      console.log("[BNP Gemini] Send button clicked");
    } else {
      console.log("[BNP Gemini] Send button not found. Smashing Enter key...");

      // Spam Enter key events. Frameworks listen to different Enter properties
      const events = [
        new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }),
        new KeyboardEvent("keypress", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }),
        new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true })
      ];
      events.forEach(ev => inputEl.dispatchEvent(ev));
    }

    // Double check if text remained in the input box, which implies sending failed (or UI didn't sync)
    // SPEED: Increased delay to 3500ms. Gemini's complex Angular UI can be slow to clear.
    await delay(250);

    const checkText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
    const currentTurnCount = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"]').length;

    // Panic only if BOTH the box is still full AND no new message turn appeared
    if (checkText.length > 20 && currentTurnCount <= previousTurnCount) {
      // Finding ANY button as a last resort panic measure
      console.warn("[BNP Gemini] Text remained in box! Send failed. Panic clicking any send button...");
      const buttons = document.querySelectorAll('button, [role="button"]');
      for (const b of buttons) {
        const html = b.outerHTML.toLowerCase();
        if ((html.includes('send') || html.includes('submit')) && !b.disabled) {
          simulateClick(b);
          await delay(50);
        }
      }

      // Final SUPER-FALLBACK: If text STILL remains, just force clear it.
      // Sometimes Gemini's internal state sends the data but fails to clear the visual box.
      await delay(150);
      const stillText = (inputEl.value || inputEl.innerText || inputEl.textContent || "").trim();
      if (stillText.length > 0) {
        console.log("[BNP Gemini] Force clearing persistent text from input box.");
        if (inputEl.tagName === "TEXTAREA" || inputEl.tagName === "INPUT") {
          inputEl.value = "";
        } else {
          inputEl.innerHTML = "";
          inputEl.innerText = "";
        }
        inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }

    await watchForResponse(previousResponseText, previousTurnCount);
  }

  // ─── Find Send Button ──────────────────────────────────────
  async function findSendButton(inputEl) {
    const selectors = [
      'button[aria-label*="Send"]',
      'button[aria-label*="send"]',
      'button[mattooltip*="Send"]',
      'button[data-test-id*="send"]',
      '.send-button',
      'button[type="submit"]',
      'path[d="M3 20V14L11 12L3 10V4L22 12Z"]', // specific svg icon
      // Broad visual selectors for the send button container
      '.text-input-field-action-button',
      'button.mat-mdc-tooltip-trigger'
    ];

    let foundBtn = null;

    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        foundBtn = el.closest("button") || el;
        break;
      }
    }

    // Look closely in the same container as the input element
    if (!foundBtn && inputEl) {
      // Go up a few DOM levels to find the chat box wrapper
      let container = inputEl;
      for (let i = 0; i < 5; i++) {
        if (!container.parentElement) break;
        container = container.parentElement;
        const btns = container.querySelectorAll('button');
        if (btns.length > 0) {
          // The send button is usually the last button in the chat box row
          foundBtn = btns[btns.length - 1];
          break;
        }
      }
    }

    if (!foundBtn) {
      const allButtons = document.querySelectorAll("button");
      for (const btn of allButtons) {
        const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
        const tooltip = (btn.getAttribute("mattooltip") || "").toLowerCase();
        if (aria.includes("send") || tooltip.includes("send")) {
          foundBtn = btn;
          break;
        }
      }
    }

    // ─── CRITICAL MINIMIZED-TAB FIX ───
    // When Chrome is minimized, Angular suspends its UI change detection.
    // The button will be permanently stuck in `disabled=true` because the framework
    // hasn't realized we injected text. We must FORCE enable it.
    if (foundBtn) {
      foundBtn.disabled = false;
      foundBtn.removeAttribute("disabled");
      foundBtn.setAttribute("aria-disabled", "false");
      // Remove any framework-specific disabled classes if they block pointer events
      foundBtn.classList.remove("disabled", "mat-button-disabled", "mdc-button--disabled");
    }

    return foundBtn;
  }

  // ─── Helper function for deeply simulated clicks ───────────
  function simulateClick(element) {
    if (!element) return;
    try {
      element.click(); // Standard click first
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

  // ─── Response Watching ──────────────────────────────────────
  // ─── Promise-based MutationObserver LLM Detection ───────────
  function waitForLLMComplete(selector, previousResponseText, previousTurnCount = 0) {
    return new Promise((resolve) => {
      console.log(`[BNP Gemini] Engaging MutationObserver for DOM Idle detection (${previousTurnCount} prior turns)...`);
      const startTime = Date.now();
      const MAX_TIMEOUT = 60000;
      const IDLE_THRESHOLD = 1000; // SPEED: Reduced from 3.5s to 1s
      const MIN_WAIT_MS = 1500;    // SPEED: Reduced from 4s to 1.5s

      let idleTimer = null;
      let lastTextLength = 0;
      let hasStartedGenerating = false;

      // ── Turn-Count Detection ──
      // Instead of relying solely on text comparison (which fails when AI gives
      // an identical reply), we track whether a NEW model turn container appeared.
      // Updated for Gemini 2026 DOM: uses <model-response> custom element
      const hasNewTurn = () => {
        const allTurns = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"]');
        return allTurns.length > previousTurnCount;
      };

      const finishAndResolve = (reason) => {
        if (idleTimer) clearTimeout(idleTimer);
        observer.disconnect();
        console.log(`[BNP Gemini] LLM Complete via: ${reason}`);

        const finalCheck = getLatestResponse();

        // If a NEW model turn appeared, trust it — the text IS the new response
        // even if it's identical to the previous one (e.g. repeated greeting).
        if (hasNewTurn()) {
          resolve(finalCheck || null);
        } else {
          // No new turn appeared — fall back to text comparison
          if (finalCheck && !isOldResponse(finalCheck, previousResponseText)) {
            resolve(finalCheck);
          } else {
            resolve(null);
          }
        }
      };

      const resetIdleTimer = () => {
        if (idleTimer) clearTimeout(idleTimer);
        if (hasStartedGenerating) {
          idleTimer = setTimeout(() => {
            // ── Minimum Wait Floor ──
            // Don't resolve prematurely — Custom Gem Analysis phases can
            // cause multi-second DOM silence before actual generation starts.
            const elapsed = Date.now() - startTime;
            if (elapsed < MIN_WAIT_MS) {
              console.log(`[BNP Gemini] Idle fired but only ${elapsed}ms elapsed (min: ${MIN_WAIT_MS}ms). Resetting...`);
              resetIdleTimer();
              return;
            }

            const resp = getLatestResponse() || "";

            // CRITICAL JSON INTEGRITY: Don't resolve if JSON is unclosed
            const trimmed = resp.trim();
            if (trimmed.startsWith("{") && !trimmed.endsWith("}")) {
              console.log("[BNP Gemini] JSON incomplete. Waiting another cycle...");
              resetIdleTimer();
              return;
            }

            if (resp.includes("⏳ [Generating...]")) {
              resetIdleTimer();
              return;
            }

            // Check UI markers to see if it's still thinking before giving up
            const turnContainer = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"]');
            if (turnContainer.length > 0) {
              const lastTurn = turnContainer[turnContainer.length - 1];
              let isStillThinking = lastTurn.querySelector('[aria-busy="true"], .thinking-icon, .thinking, mat-progress-bar, mat-spinner, [role="progressbar"], .loading-indicator, .spinner, .analyzing-icon, .analysis, [aria-label*="Analysis"], [aria-label*="analysis"]');
              if (isStillThinking || resp.trim().endsWith("Analysis") || resp.trim().endsWith("Thinking...")) {
                console.log("[BNP Gemini] Idle timer hit, but UI is still 'Thinking/Analyzing'. Waiting...");
                resetIdleTimer();
                return;
              }

              // No copy button + no text = still generating, don't give up yet
              const hasCopyBtn = lastTurn.querySelector('button[aria-label*="Copy"], [aria-label*="copy message"], button[mattooltip*="Copy"]');
              if (!hasCopyBtn && !resp) {
                console.log("[BNP Gemini] No copy button and no text yet. Waiting...");
                resetIdleTimer();
                return;
              }
            }

            finishAndResolve("DOM Idle Timeout (3500ms)");
          }, IDLE_THRESHOLD);
        }
      };

      const observer = new MutationObserver(() => {
        if (Date.now() - startTime > MAX_TIMEOUT) {
          finishAndResolve("Hard Timeout (60s)");
          return;
        }

        const currentText = getLatestResponse() || "";

        // ── Generation Start Detection ──
        // Use BOTH structural (new turn appeared) and textual (new text) detection.
        // This fixes the bug where isOldResponse() fails on identical replies.
        if (!hasStartedGenerating) {
          const newTurnExists = hasNewTurn();
          const isNewText = currentText && !isOldResponse(currentText, previousResponseText);

          if (newTurnExists || isNewText) {
            hasStartedGenerating = true;
            console.log(`[BNP Gemini] Detected new generation start! (newTurn: ${newTurnExists}, newText: ${isNewText})`);
            resetIdleTimer();
          }
        }

        if (hasStartedGenerating && !currentText.includes("⏳ [Generating...]")) {
          // Hybrid UI stops check
          const turnContainer = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"]');
          let isThinking = false;
          let hasCopyBtn = false;

          if (turnContainer.length > 0) {
            const lastTurn = turnContainer[turnContainer.length - 1];
            isThinking = lastTurn.querySelector('[aria-busy="true"], .thinking-icon, .thinking, mat-progress-bar, mat-spinner, [role="progressbar"], .loading-indicator, .spinner, .analyzing-icon, .analysis, [aria-label*="Analysis"], [aria-label*="analysis"]');

            // Extra check: if the text itself ends with "Analysis" or "Thinking"
            if (!isThinking && (currentText.trim().endsWith("Analysis") || currentText.trim().endsWith("Thinking..."))) {
              isThinking = true;
            }

            hasCopyBtn = lastTurn.querySelector('button[aria-label*="Copy"], [aria-label*="copy message"], button[mattooltip*="Copy"]');
          }

          if (currentText.length !== lastTextLength) {
              lastTextLength = currentText.length;
              resetIdleTimer();
              if (currentText.trim() && currentRequestId) {
                  sendResponse(currentRequestId, cleanResponseText(currentText), [], "partial");
              }
          } else if (hasCopyBtn && !isThinking) {
            // Strong UI signal that generation is complete. Trust the fast idle.
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

      setTimeout(() => finishAndResolve("Failsafe Hard Timeout (60s)"), MAX_TIMEOUT);
    });
  }

  // ─── Response Flow Execution ────────────────────────────────
  async function watchForResponse(previousResponseText, previousTurnCount = 0) {
    if (typeof responseObserver !== 'undefined' && responseObserver) {
      responseObserver.disconnect();
    }

    const rawFinalText = await waitForLLMComplete("body", previousResponseText, previousTurnCount);

    const logId = currentRequestId.substring(0, 8);
    const logMsg = (msg) => {
      console.log(`[BNP Gemini] [${logId}] ${msg}`);
      window.dispatchEvent(new CustomEvent("bnp-log", { detail: { source: "Gemini", text: `[${logId}] ${msg}` } }));
      chrome.runtime.sendMessage({ type: "BNP_LOG", source: "Gemini", text: `[${logId}] ${msg}` });
    };

    if (!rawFinalText) {
      logMsg("Response timeout");
      sendErrorResponse(currentRequestId, "Timeout: AI did not write a new response.");
      return;
    }

    logMsg("Stability reached. Finalizing capture...");

    const trimmed = rawFinalText.trim();
    const greedDelay = trimmed.startsWith("{") ? 50 : 150;
    await delay(greedDelay);

    const suspectLog = rawFinalText.toLowerCase();
    const suspectImage = suspectLog.includes("generate") ||
      suspectLog.includes("image") || suspectLog.includes("visual") ||
      suspectLog.includes("duck") || suspectLog.includes("bird") ||
      suspectLog.includes("earth") || suspectLog.includes("cat") || suspectLog.includes("photo");

    captureTextViaCopyButton(logMsg).then(async (qualityText) => {
      let finalResult = qualityText || rawFinalText;

      if (!qualityText && finalResult) {
        logMsg("Warning: Using fallback DOM text. Style might be degraded.");
      }

      if (finalResult && (finalResult.startsWith("✨ [Visual Content Rendered") || finalResult.startsWith("✨ [Visual Content Generated"))) {
        finalResult = "✨ [Visual Content Generated]";
      } else {
        finalResult = cleanResponseText(finalResult);
      }

      let extractedImages = [];
      const isVisual = suspectImage || (finalResult && finalResult.startsWith("✨"));
      
      if (isVisual) {
        logMsg("Visual request detected. Waiting extra for pixels...");
        await delay(1500);
      }

      try {
        logMsg("Starting greedy image scan...");
        // SPEED: Only do 5 retries (10s) if we suspect an image. Otherwise, do 1 fast pass.
        extractedImages = await getLatestImages(logMsg, isVisual ? 5 : 1);
        logMsg(`Scan completed. Success: ${extractedImages.length > 0} (${extractedImages.length} imgs)`);
      } catch (err) {
        logMsg(`Greedy scan error: ${err.message}`);
      }

      sendResponse(currentRequestId, finalResult, extractedImages, "finished");
    });
  }



  // ─── Native Image Generation Monitor ────────────────────────
  async function waitForImagesToFinish(turnElement, logMsg) {
    if (logMsg) logMsg("Waiting for AI Artwork to finish...");
    let isBusy = true;
    let attempts = 0;
    while (isBusy && attempts < 25) {
      // Look for Gemini's specific "Generating" or loading states
      const loaders = turnElement.querySelectorAll('.generating-icon, .loading-indicator, .image-placeholder, .skeleton, .pulsing, .loading, [aria-busy="true"]');
      const progress = turnElement.querySelector('mat-progress-bar, .loading-spinner, .img-loading');

      // NEW: The "Download" button is the absolute proof that it's finished!
      const hasDownloadBtn = turnElement.querySelector('mat-icon[fonticon="download"], [aria-label*="Download"], .button-icon-wrapper');

      if (hasDownloadBtn) {
        if (logMsg) logMsg("Download button detected! Generation ready.");
        isBusy = false;
        break;
      }

      if (loaders.length === 0 && !progress) {
        const hasImages = turnElement.querySelectorAll('img').length > 0;
        if (hasImages || attempts > 8) {
          isBusy = false;
        }
      }

      if (isBusy) {
        await delay(250);
        attempts++;
      }
    }
    if (logMsg) logMsg("Artwork seems stable. Finalizing pixels...");
    await delay(250);
  }

  // ─── Extract Latest Images ──────────────────────────────────
  // ─── Extract Latest Images ──────────────────────────────────
  async function getLatestImages(logMsg, maxRetries = 5) {
    let images = [];

    for (let r = 0; r < maxRetries; r++) {
      // Strategy 0: Gemini 2026 — <generated-image> / <single-image> custom elements
      // This is the highest-priority strategy for the new Gemini DOM
      const genImgElements = document.querySelectorAll('generated-image img, single-image img, .generated-image img');
      for (const img of genImgElements) {
        const url = img.src || "";
        const fp = getImageFingerprint(img);
        if (url && fp && !sentImageFingerprints.has(fp) && isValidForResult(img, logMsg, true)) {
          logMsg(`Gemini 2026 Capture: Found NEW generated image via <generated-image> (${url.substring(0, 40)}...)`);
          images.push(img);
        }
      }

      // Strategy 1: Global search for generated images (broadened URL filter)
      if (images.length === 0) {
        const allImgs = Array.from(document.querySelectorAll('img'));
        const generatedImgs = allImgs.filter(img => {
          const url = img.src || "";
          return (url.includes('googleusercontent.com') || url.startsWith('blob:') || url.startsWith('data:image'));
        });

        for (const img of generatedImgs) {
          const fp = getImageFingerprint(img);
          if (fp && !sentImageFingerprints.has(fp) && isValidForResult(img, logMsg, true)) {
            logMsg("Global Capture: Found NEW generated image in DOM.");
            images.push(img);
          }
        }
      }

      // Strategy 2: Look in the last 3 model turns (updated selectors)
      if (images.length === 0) {
        const turns = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"], .model-response');
        if (turns.length > 0) {
          const recentTurns = Array.from(turns).slice(-3);
          for (const turn of recentTurns) {
            const turnImgs = turn.querySelectorAll('img');
            for (const img of turnImgs) {
              if (isValidForResult(img, logMsg) && (!getImageFingerprint(img) || !sentImageFingerprints.has(getImageFingerprint(img)))) {
                logMsg("Turn-based Capture: Found NEW image in recent turn.");
                images.push(img);
              }
            }
          }
        }
      }

      if (images.length > 0) break;
      await delay(500);
    } // End of retry loop

    // Mark found images as sent to avoid duplicates (using fingerprints)
    images.forEach(img => {
      const fp = getImageFingerprint(img);
      if (fp) sentImageFingerprints.add(fp);
    });

    const processedDatas = [];
    for (const img of images) {
      // PROACTIVE: Trigger the native download button
      try {
        const btm = img.closest('model-response, .model-response, [data-turn-role="model"], [data-message-author-role="model"]');
        const dlBtn = btm?.querySelector('.download-icon, mat-icon.download-icon, mat-icon[fonticon="download"], [aria-label*="Download"]');
        if (dlBtn) {
          logMsg("Native Trigger: Clicking download button...");
          dlBtn.click();
        }
      } catch (e) {
        logMsg(`Native Trigger Error: ${e.message}`);
      }

      const data = await imageToDataURL(img, logMsg);
      if (data) processedDatas.push(data);
    }

    return [...new Set(processedDatas)];
  }

  function isValidForResult(img, logMsg, isGlobal = false) {
    const src = img.src || "";
    if (!src || src.includes('avatar') || src.includes('profile') || src.includes('icon')) return false;

    // Reject UI vectors and SVGs to avoid Telegram API breaking, but allow Youtube/third-party thumbnails
    if (src.includes('.svg') || src.startsWith('data:image/svg')) return false;

    // IMMEDIATELY REJECT user attachment thumbnails or images in user prompt bubbles
    if (img.closest('file-attachment-chip, gallery-item, .file-chip, .user-message, [data-message-author-role="user"], [data-turn-role="user"], user-query')) {
      return false;
    }

    const isGeneratedSrc = src.includes('googleusercontent.com') ||
      src.includes('imagestore') ||
      src.includes('content-focus') ||
      src.includes('generated') ||
      src.includes('ggpht.com') ||
      src.startsWith('blob:') ||
      src.startsWith('data:image');

    // Updated for Gemini 2026: use custom elements + legacy selectors
    const turnContainer = img.closest('model-response, response-container, structured-content-container, [data-turn-role], [data-message-author-role], .model-response, .model-response-text, .response-container');
    const isInResponse = turnContainer && (
      turnContainer.tagName === 'MODEL-RESPONSE' ||
      turnContainer.tagName === 'RESPONSE-CONTAINER' ||
      turnContainer.classList?.contains('model-response-text') ||
      turnContainer.dataset?.turnRole === 'model' ||
      turnContainer.dataset?.messageAuthorRole === 'model' ||
      turnContainer.classList?.contains('model-response') ||
      turnContainer.classList?.contains('response-container')
    );

    // Gemini 2026: check if image is inside <generated-image> or <single-image>
    const isInGeneratedImage = !!img.closest('generated-image, single-image, .generated-image');

    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    const isBig = (w >= 100 || h >= 100);

    const hasDownloadBtn = turnContainer?.querySelector('mat-icon[fonticon="download"], .download-icon, .button-icon-wrapper, [aria-label*="Download"], a[download], button[aria-label*="download"]');
    const isImageGenerationUI = img.closest('.image-item, .image-generation-container, [class*="image-container"], .image-container, .generated-images');

    const valid = isInGeneratedImage || (isInResponse && isBig) || hasDownloadBtn || isImageGenerationUI || (isGeneratedSrc && isBig);
    if (valid && logMsg) logMsg(`Validated pixels: ${w}x${h} | Src: ${src.substring(0, 30)}...`);
    return valid;
  }

  async function imageToDataURL(imgElement, logMsg) {
    const url = imgElement.src;
    if (!url || url.startsWith('data:image/svg')) return null;

    // If it's already a data URL, return it directly
    if (url.startsWith('data:image/')) {
      if (logMsg) logMsg(`Image already Base64 (${url.length} chars)`);
      return url;
    }

    if (logMsg) logMsg(`Capturing Binary Data for: ${url.substring(0, 40)}...`);

    // ═══════════════════════════════════════════════════════════
    // FAST PATH: Canvas capture for blob: URLs
    // Blob URLs are scoped to the tab that created them — they CANNOT be
    // fetched by background workers or downloaded via chrome.downloads.
    // Canvas drawImage works perfectly since they're same-origin.
    // ═══════════════════════════════════════════════════════════
    if (url.startsWith('blob:')) {
      try {
        if (logMsg) logMsg(`Blob URL detected — using direct canvas capture...`);
        // Wait for image to be fully loaded
        if (!imgElement.complete) {
          await new Promise((resolve) => {
            imgElement.onload = resolve;
            imgElement.onerror = resolve;
            setTimeout(resolve, 5000);
          });
        }
        const canvas = document.createElement("canvas");
        canvas.width = imgElement.naturalWidth || imgElement.width;
        canvas.height = imgElement.naturalHeight || imgElement.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(imgElement, 0, 0);
        const data = canvas.toDataURL("image/png");
        if (data && data.length > 100) {
          if (logMsg) logMsg(`Blob Canvas Success! (${data.length} chars, ${canvas.width}x${canvas.height})`);
          return data;
        }
      } catch (e) {
        if (logMsg) logMsg(`Blob canvas capture failed: ${e.message}`);
      }
    }

    // ═══════════════════════════════════════════════════════════
    // Strategy A: BACKGROUND DOWNLOAD API (Nuclear Option)
    // The background service worker uses chrome.downloads.download()
    // to bypass CORS entirely, saves the file to disk, reads it
    // locally, encodes to Base64, and then deletes the file.
    // ═══════════════════════════════════════════════════════════
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
      } else {
        if (logMsg) logMsg(`Downloads API fetch failed: ${mainWorldResponse?.error || "Empty data"}`);
      }
    } catch (e) {
      if (logMsg) logMsg(`Downloads API fetch Exception: ${e.message}`);
    }

    // Strategy B: Inline script injection (fallback if scripting API unavailable)
    try {
      if (logMsg) logMsg(`Trying inline MAIN WORLD fetch...`);
      const dataUrl = await mainWorldFetch(url);
      if (dataUrl && dataUrl.length > 100) {
        if (logMsg) logMsg(`Inline MAIN WORLD fetch Success! (${dataUrl.length} chars)`);
        return dataUrl;
      }
    } catch (e) {
      if (logMsg) logMsg(`Inline MAIN WORLD fetch failed: ${e.message}`);
    }

    // Strategy C: Background service worker fetch
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
      } else {
        if (logMsg) logMsg(`Background fetch failed: ${bgResponse?.error || "Empty data"}`);
      }
    } catch (e) {
      if (logMsg) logMsg(`Background fetch Exception: ${e.message}`);
    }

    // Strategy D: Direct canvas (works for same-origin/blob images)
    try {
      const canvas = document.createElement("canvas");
      canvas.width = imgElement.naturalWidth || imgElement.width;
      canvas.height = imgElement.naturalHeight || imgElement.height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(imgElement, 0, 0);
      const data = canvas.toDataURL("image/png");
      if (data && data.length > 100) {
        if (logMsg) logMsg(`Canvas Direct Success! (${data.length} chars)`);
        return data;
      }
    } catch (e) {
      if (logMsg) logMsg(`Canvas direct failed: ${e.message}`);
    }

    if (logMsg) logMsg(`All image capture strategies exhausted for: ${url.substring(0, 40)}`);
    return null;
  }

  /**
   * Inject a fetch call into the PAGE's MAIN world via a <script> tag.
   * This runs with the page's own origin and cookies, allowing access
   * to authenticated Google image URLs that cross-origin fetches can't reach.
   */
  function mainWorldFetch(imageUrl) {
    return new Promise((resolve, reject) => {
      const callbackId = '_bnp_img_' + Math.random().toString(36).substr(2, 9);
      const timeoutHandle = setTimeout(() => {
        window.removeEventListener('message', handler);
        reject(new Error('Main world fetch timeout'));
      }, 20000);

      function handler(event) {
        if (event.data && event.data.type === callbackId) {
          window.removeEventListener('message', handler);
          clearTimeout(timeoutHandle);
          if (event.data.dataUrl) {
            resolve(event.data.dataUrl);
          } else {
            reject(new Error(event.data.error || 'Unknown error'));
          }
        }
      }
      window.addEventListener('message', handler);

      // Inject script into the page's MAIN world
      const script = document.createElement('script');
      script.textContent = `
        (async function() {
          try {
            const resp = await fetch(${JSON.stringify(imageUrl)}, {
              credentials: 'include',
              mode: 'cors'
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const blob = await resp.blob();
            const reader = new FileReader();
            reader.onloadend = function() {
              window.postMessage({ type: ${JSON.stringify(callbackId)}, dataUrl: reader.result }, '*');
            };
            reader.onerror = function() {
              window.postMessage({ type: ${JSON.stringify(callbackId)}, error: 'FileReader error' }, '*');
            };
            reader.readAsDataURL(blob);
          } catch(e) {
            window.postMessage({ type: ${JSON.stringify(callbackId)}, error: e.message }, '*');
          }
        })();
      `;
      document.documentElement.appendChild(script);
      script.remove(); // Clean up the script tag immediately
    });
  }

  // ─── High Quality Copy Strategy ─────────────────────────────
  // ─── Extract Full Answer (Explanation + Code + Context) ──────
  // Used as fallback when copy buttons fail
  function extractFullAnswer(turn, logMsg) {
    try {
      let fullText = '';
      
      // Get all direct content from the turn container
      // Visit all child nodes in order to preserve structure
      const processNode = (node) => {
        if (node.nodeType === Node.TEXT_NODE) {
          const text = node.textContent.trim();
          if (text.length > 0 && !text.match(/^\s*$/)) {
            fullText += text + '\n';
          }
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          const tag = node.tagName.toLowerCase();
          
          // Handle code blocks - add them with markdown formatting
          if (tag === 'code' || tag === 'pre' || node.classList.contains('code-block')) {
            const codeText = (node.textContent || '').trim();
            if (codeText.length > 10) {
              fullText += '\n```\n' + codeText + '\n```\n';
            }
          } 
          // Handle lists
          else if (tag === 'ul' || tag === 'ol') {
            Array.from(node.children).forEach(li => {
              if (li.tagName.toLowerCase() === 'li') {
                fullText += '• ' + (li.textContent || '').trim() + '\n';
              }
            });
          }
          // Handle headings
          else if (tag.match(/^h[1-6]$/)) {
            fullText += '\n' + (node.textContent || '').trim() + '\n';
          }
          // Handle paragraphs and divs - recurse into them
          else if (tag === 'p' || tag === 'div' || tag === 'span' || tag === 'message-content' || tag === 'structured-content-container') {
            Array.from(node.childNodes).forEach(child => processNode(child));
          }
          // For other elements, try to get text content
          else if (tag !== 'button' && tag !== 'script' && tag !== 'style') {
            const text = (node.textContent || '').trim();
            if (text.length > 0 && !text.match(/^\s*$/) && !node.querySelector('button')) {
              fullText += text + '\n';
            }
          }
        }
      };
      
      // Process all direct children of the response turn
      Array.from(turn.childNodes).forEach(child => {
        // Skip buttons and other UI elements
        if (child.nodeType === Node.ELEMENT_NODE && !child.querySelector('button[aria-label*="Copy"]')) {
          processNode(child);
        } else if (child.nodeType === Node.TEXT_NODE) {
          processNode(child);
        }
      });
      
      // Clean up excessive whitespace
      fullText = fullText
        .replace(/\n\n\n+/g, '\n\n')  // Multiple newlines to double newline
        .replace(/\s+$/gm, '')         // Trailing spaces on each line
        .trim();
      
      return fullText.length > 50 ? fullText : null;
    } catch (e) {
      if (logMsg) logMsg(`extractFullAnswer error: ${e.message}`);
      return null;
    }
  }

  async function captureTextViaCopyButton(logMsg) {
    try {
      const lastTurn = document.querySelectorAll('model-response, [data-turn-role="model"], [data-message-author-role="model"]');
      if (lastTurn.length === 0) return null;

      const turn = lastTurn[lastTurn.length - 1];

      // Reset the capture flag
      capturedClipboardText = null;

      // Strategy A: Try the MAIN response copy button first
      const copyBtn = turn.querySelector('button[aria-label*="Copy"], [aria-label*="copy message"], button[mattooltip*="Copy"]');

      if (copyBtn) {
        if (logMsg) logMsg("High-Fidelity Mode: Simulating official Copy action...");
        simulateClick(copyBtn);

        // Polling wait for the interceptor to catch the data
        // SPEED: Reduced to 15 steps (750ms) from 60 steps (3s)
        for (let i = 0; i < 15; i++) {
          if (capturedClipboardText && capturedClipboardText.length > 5) {
            if (logMsg) logMsg(`Success! Raw Markdown Captured (${capturedClipboardText.length} chars) (${(i + 1) * 50}ms)`);
            return capturedClipboardText;
          }
          await delay(25);
        }
        if (logMsg) logMsg("Main Copy button did not yield clipboard data.");
      }

      // Strategy B: Try code block copy buttons (when response is wrapped in a code block)
      // Gemini's code block containers have their own copy buttons
      capturedClipboardText = null;
      const codeBlockCopyBtns = turn.querySelectorAll('code-block button, .code-block button, [class*="code-block"] button, pre + button, .code-header button');
      for (const codeBtn of codeBlockCopyBtns) {
        const ariaLabel = (codeBtn.getAttribute('aria-label') || '').toLowerCase();
        const tooltip = (codeBtn.getAttribute('mattooltip') || '').toLowerCase();
        const btnText = (codeBtn.textContent || '').toLowerCase();
        if (ariaLabel.includes('copy') || tooltip.includes('copy') || btnText.includes('copy')) {
          if (logMsg) logMsg("Trying code block copy button...");
          simulateClick(codeBtn);
          for (let i = 0; i < 30; i++) {
            if (capturedClipboardText && capturedClipboardText.length > 5) {
              if (logMsg) logMsg(`Code Block Copy Success! (${capturedClipboardText.length} chars) (${(i + 1) * 50}ms)`);
              return capturedClipboardText;
            }
            await delay(25);
          }
          break; // Only try the first code copy button
        }
      }

      // Strategy C: Extract FULL answer container (all text + code blocks)
      // Build the complete answer by combining all content in order, not just the code block
      const fullAnswerText = extractFullAnswer(turn, logMsg);
      if (fullAnswerText && fullAnswerText.length > 50) {
        if (logMsg) logMsg(`Full Answer Extraction (${fullAnswerText.length} chars)`);
        return fullAnswerText;
      }

      if (logMsg) logMsg("All copy strategies exhausted. Falling back to DOM text.");
      return null;
    } catch (e) {
      return null;
    }
  }

  // ─── Helper for old text fuzzy matching ─────────────────────

  // ─── Helper for old text fuzzy matching ─────────────────────
  function isOldResponse(newText, oldText) {
    if (!oldText) return false;
    const cleanNew = newText.trim().replace(/\s+/g, ' ');
    const cleanOld = oldText.trim().replace(/\s+/g, ' ');

    if (cleanNew === cleanOld) return true;

    // Check if new text is just a minor variation (citations loading)
    if (cleanNew.startsWith(cleanOld) && cleanNew.length < cleanOld.length + 20) {
      return true;
    }
    return false;
  }

  // ─── Extract Latest Response ────────────────────────────────
  function getLatestResponse() {
    // Gemini 2026 renders responses in custom elements: <model-response>, <message-content>, etc.
    const selectors = [
      'model-response message-content',
      'model-response .model-response-text',
      'structured-content-container.model-response-text',
      'div[data-message-author-role="model"] .message-content',
      'div[data-turn-role="model"] .message-content',
      'model-response',
      ".model-response",
      ".model-response-text",
      ".response-content",
      'div[data-message-author-role="model"]',
      'div[data-turn-role="model"]'
    ];

    let responseElements = [];

    for (const sel of selectors) {
      const els = document.querySelectorAll(sel);
      if (els.length > 0) {
        responseElements = Array.from(els);
        if (responseElements.length > 0) break;
      }
    }

    if (responseElements.length === 0) {
      // Broad fallback: look for the last model turn (updated for 2026 DOM)
      const turns = document.querySelectorAll('model-response, [data-turn-role="model"], .model-response, [data-message-author-role="model"]');
      if (turns.length > 0) {
        responseElements = [turns[turns.length - 1]];
      }
    }

    if (responseElements.length === 0) return null;

    // Get the last response element's text
    // Start from the latest and look for one that has actual content
    let lastEl = null;
    for (let i = responseElements.length - 1; i >= 0; i--) {
      const el = responseElements[i];
      const rawText = (el.innerText || el.textContent || "").trim();
      const hasImages = el.querySelector('img') !== null;

      // List of phrases that indicate a status-only bubble
      const statusPhrases = ["you stopped this response", "show thinking", "thinking...", "thought for"];
      const isStatusOnly = statusPhrases.some(p => rawText.toLowerCase().includes(p)) && !hasImages;

      if (isStatusOnly && i > 0) {
        continue; // Keep looking back for real content
      }

      lastEl = el;
      break;
    }

    if (!lastEl) lastEl = responseElements[responseElements.length - 1]; // absolute fallback

    // Get the closest turn container for comprehensive text extraction (updated for Gemini 2026)
    let turnContainer = null;
    if (lastEl) {
      turnContainer = lastEl.closest('model-response, [data-turn-role="model"], [data-message-author-role="model"], .model-response')
        || lastEl.parentNode?.parentNode
        || lastEl;
    }

    if (!turnContainer) turnContainer = lastEl;


    // ──────────────────────────────────────────────────────────
    // DEEP TEXT EXTRACTION
    // Gemini's "thinking" model and code block rendering can
    // cause innerText to return only a tiny fragment.
    // ──────────────────────────────────────────────────────────
    let text = "";
    // Create a clone to safely modify DOM artifacts
    const clone = turnContainer.cloneNode(true);

    // Recover Markdown bold/italic UI tags back into literal format (helps with __name__)
    clone.querySelectorAll?.('strong, b').forEach(node => {
      // SKIP if inside a code block to avoid breaking literal code (like __name__)
      if (node.closest('pre, code, [class*="code"], [class*="syntax"]')) return;
      const marker = document.createTextNode('__' + node.textContent + '__');
      node.parentNode.replaceChild(marker, node);
    });
    clone.querySelectorAll?.('em, i').forEach(node => {
      if (node.closest('pre, code, [class*="code"], [class*="syntax"]')) return;
      const marker = document.createTextNode('_' + node.textContent + '_');
      node.parentNode.replaceChild(marker, node);
    });
    clone.querySelectorAll?.('u').forEach(node => {
      const marker = document.createTextNode('<u>' + node.textContent + '</u>');
      node.parentNode.replaceChild(marker, node);
    });

    // Recover block-level line breaks because unattached nodes lose innerText formatting
    clone.querySelectorAll?.('br').forEach(node => {
      node.parentNode.replaceChild(document.createTextNode('\n'), node);
    });
    clone.querySelectorAll?.('p, div').forEach(node => {
      node.appendChild(document.createTextNode('\n\n'));
    });
    clone.querySelectorAll?.('li').forEach(node => {
      const marker = document.createTextNode('- ' + node.textContent + '\n');
      node.parentNode.replaceChild(marker, node);
    });

    // Strategy 1: Safely use textContent now that newlines are injected
    let fullTurnText = (clone?.textContent?.trim() || "").replace(/\n{3,}/g, '\n\n').trim();

    // ── GIGANTIC RESPONSE FIX (Aggressive Turn Extraction) ──
    // Strategy: We want the FULL turn content, not just the last message fragment.
    // 1. Traverse the clone and collect all "content" nodes (P, LI, PRE, CODE, message-content)
    // 2. Fall back to a full text walker if fragments are still too short.
    
    // Check if we captured enough. If not, try common turn ancestors.
    if (!fullTurnText || fullTurnText.length < 100) {
        logEvent('DEBUG', 'Response too short, attempting wide-area extraction...');
        const contentContainers = clone.querySelectorAll('message-content, .message-content, .model-response-text, p, li, pre');
        if (contentContainers.length > 1) {
            // Join all primary content blocks
            let combined = "";
            contentContainers.forEach(cc => {
                const cText = cc.textContent?.trim();
                if (cText && !combined.includes(cText)) {
                    combined += cText + "\n\n";
                }
            });
            if (combined.length > fullTurnText.length) fullTurnText = combined.trim();
        }
    }

    // Final scrub: If the text is still empty, use a universal text walker on the clone
    if (!fullTurnText || fullTurnText.length < 10) {
      const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT, null, false);
      let t_node, parts = [];
      const skipTerms = ["Gemini said", "Copy code", "Edit response", "Good response", "Bad response"];
      while (t_node = walker.nextNode()) {
        const t = t_node.textContent.trim();
        if (t && !skipTerms.some(term => t.includes(term))) {
            parts.push(t);
        }
      }
      if (parts.length > 0) fullTurnText = parts.join(" ");
    }

    if (fullTurnText.length > 0) {
      text = fullTurnText;
    }

    // Strategy 0: Simple innerText fallback check
    // If the turnContainer's innerText is vastly longer than our processed text, trust it
    // (but sanitized of UI labels)
    const rawInner = (turnContainer.innerText || "").trim();
    if (rawInner.length > text.length * 1.5) {
        // High confidence that simple innerText is more complete
        text = rawInner.replace(/Copy code|Gemini said|Edit response/g, "").trim();
    }

    // Strategy 1: Extract text from code blocks (Only as a absolute last resort fallback)
    if (!text || text.length < 20) {
      logEvent('DEBUG', 'No text found, trying code-block only extraction...');
      const codeBlocks = clone?.querySelectorAll?.('code-block, .code-block, pre code, .code-block-decoration + pre, [class*="code-block"]') || [];
      if (codeBlocks.length > 0) {
        const codeTexts = [];
        const seenTexts = new Set();
        for (const cb of codeBlocks) {
          const codeEl = cb.querySelector('code') || cb;
          const codeText = (codeEl?.textContent || codeEl?.innerText || "").trim();
          if (codeText.length > 5 && !seenTexts.has(codeText)) {
            seenTexts.add(codeText);
            codeTexts.push(codeText);
          }
        }
        if (codeTexts.length > 0) {
          const combined = codeTexts.join("\n\n");
          // ONLY set if we have NOTHING else. Do not overwrite partial explanations.
          if (!text || combined.length > text.length) {
              text = combined;
          }
        }
      }
    }

    // Strategy 2: Content nodes excluding "thinking"
    if (!text || text.length < 50) {
      const thinkingSection = clone?.querySelector?.('.thinking-content, [data-thinking], details.thinking, .thought-container');
      const contentNodes = Array.from(clone?.querySelectorAll?.('p, div[role="region"], article, section, .message-content, .model-response-text, .response-content, .markdown') || []);

      if (contentNodes.length > 0) {
        const topLevelNodes = contentNodes.filter((node, i) => {
          return !contentNodes.some((other, j) => i !== j && other.contains(node) && other !== node);
        });

        const allTextParts = [];
        const seenParts = new Set();
        for (const node of topLevelNodes) {
          if (thinkingSection && thinkingSection.contains(node)) continue;
          const nodeText = (node?.innerText || node?.textContent || "").trim();
          if (nodeText.length > 0 && !seenParts.has(nodeText)) {
            seenParts.add(nodeText);
            allTextParts.push(nodeText);
          }
        }
        if (allTextParts.length > 0) {
          const combined = allTextParts.join("\n").trim();
          // Final safety: Do not overwrite if we already have decent text
          if (!text || (combined.length > text.length && text.length < 100)) {
              text = combined;
          }
        }
      }
    }

    // Strategy 3: Try ALL <pre> and <code> elements
    if (!text || text.length < 50) {
      const preElements = clone?.querySelectorAll?.('pre, code') || [];
      const preParts = [];
      const seenPre = new Set();
      for (const pre of preElements) {
        const preText = (pre?.textContent || pre?.innerText || "").trim();
        if (preText.length > 10 && !seenPre.has(preText)) {
          seenPre.add(preText);
          preParts.push(preText);
        }
      }
      if (preParts.length > 0) {
        const combined = preParts.join("\n\n");
        if (!text || (combined.length > text.length && text.length < 50)) {
            text = combined;
        }
      }
    }

    // If still nothing, use the full turn text as last resort
    if (!text || text.length < 50) {
      text = fullTurnText;
    }

    const cleaned = cleanResponseText(text || null);

    // Safety: If no solid text, check visuals or generation UI
    if (!cleaned) {
      // Look for ACTUAL generated images (not avatars) — updated for Gemini 2026
      const imgs = Array.from(turnContainer?.querySelectorAll?.('img') || []);
      const hasRealImg = imgs.some(img => {
        const src = img.src || "";
        const isAvatar = src.includes('avatar') || src.includes('profile') || src.includes('icon');
        const isGenerated = src.includes('googleusercontent.com') || src.includes('imagestore') || src.startsWith('blob:');
        const w = img.naturalWidth || img.width || 0;
        return !isAvatar && (isGenerated || w > 100);
      });

      // Check for Gemini 2026 custom elements AND legacy selectors
      const hasGeneratedImageElement = turnContainer?.querySelector?.('generated-image, single-image, .generated-image, .generated-images');
      const hasVisuals = hasRealImg || hasGeneratedImageElement || turnContainer?.querySelector?.('mat-icon[fonticon="download"], .image-generation-container, .image-item');

      if (hasVisuals) {
        return `✨ [Visual Content Rendered #${responseElements.length}]`;
      }

      // Still nothing solid, keep waiting
      return null;
    }

    return cleaned;
  }

  function cleanResponseText(text) {
    if (!text) return "";
    let cleaned = text;

    // 0. Remove status and artifacts (Globally)
    cleaned = cleaned.replace(/(Show thinking|Thinking\.{0,3}|Thought for \d+ seconds?|You stopped this response|Gemini said|AI generated)/gi, "");

    // Strip Custom Gem UI headers specifically
    // The bullet '•' between BANE-NLP and Custom Gem must be handled
    // Order: most specific first → least specific last
    cleaned = cleaned.replace(/^(B\s*)?BANE-NLP\s*[•·]?\s*Custom Gem\s*Analysis\s*(?:BANE-NLP\s+)?(?:said)?\s*/gi, "");
    cleaned = cleaned.replace(/^(B\s*)?BANE-NLP\s*[•·]?\s*Custom Gem\s*/gi, "");
    cleaned = cleaned.replace(/^(B\s*)?BANE-NLP\s*(?:said)?\s*/gi, "");
    // Catch orphaned "said" if it survived the above (e.g. on a new line after header stripping)
    cleaned = cleaned.replace(/^\s*said\s*/gi, "");

    // Strip Gemini Custom Gem "Analysis" / "Query successful" UI artifacts
    // These leak from the collapsible analysis panel in Gemini's Custom Gem interface
    cleaned = cleaned.replace(/^\s*Analysis\s*\n/gim, "");
    cleaned = cleaned.replace(/^\s*[✓✔☑︎]\s*(?:Query|Analysis)\s+successful\s*\n?/gim, "");
    cleaned = cleaned.replace(/^\s*[-•–]\s*Query successful\s*\n?/gim, "");
    cleaned = cleaned.replace(/^\s*Query successful\s*\n?/gim, "");
    cleaned = cleaned.replace(/^\s*Analyzing\.{0,3}\s*\n?/gim, "");

    // Strip Source Identification Block (multi-platform routing header)
    cleaned = cleaned.replace(/═══ MESSAGE SOURCE ═══[\s\S]*?═══════════════════════\n?/g, "");
    cleaned = cleaned.replace(/^FROM: (?:TELEGRAM|MESSENGER|PORTFOLIO).*\n?/gim, "");
    cleaned = cleaned.replace(/^RESPOND VIA:.*\n?/gim, "");

    // Ensure BNP headers are excluded from output
    cleaned = cleaned.replace(/\[(KNOWLEDGE BASE|AI_SKILLS_DRIVE)\][\s\S]*?\[USER_ID: \d+\]\s*USER:.*?\n/gi, "");
    cleaned = cleaned.replace(/\[MANDATORY RULES\] MANDATORY_RULES\.txt[\s\S]*?\[USER_ID: \d+\]\s*USER:.*?\n/gi, "");
    cleaned = cleaned.replace(/\[KNOWLEDGE BASE\] BANE_CONTEXT_FILES\/BANE_NLP_BRAIN_knowledge\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[AI_SKILLS_DRIVE\] https:\/\/drive\.google\.com\/[\s\S]*?\s*/gi, "");
    cleaned = cleaned.replace(/\[MANDATORY RULES\] MANDATORY_RULES\.txt\s*/gi, "");
    cleaned = cleaned.replace(/\[WORKSPACE MAP\] WORKSPACE_ARCHITECTURE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[PROJECT CONTEXT\] ACTIVE_PROJECTS_CONTEXT\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[SCENARIOS GUIDE\] BANE_SCENARIOS\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[DEPLOYMENT_GUIDE\] AUTONOMOUS_DEPLOYMENT_GUIDE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[MCP_TOOL_GUIDE\] MCP_TOOLS_DOCUMENTATION\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[EXECUTION COMMAND\]\s*/gi, "");

    // 0b. Remove code block language labels that Gemini prepends
    // e.g., "Markdown\n### RUBY..." → "### RUBY..."
    cleaned = cleaned.replace(/^(Markdown|markdown|plaintext|text|JSON|json|Python|python|Java|java|Ruby|ruby|HTML|html|CSS|css|JavaScript|javascript)\s*\n/i, "");

    // 0c. Remove "Copy code" / "Copy" UI button text
    cleaned = cleaned.replace(/\bCopy code\b/g, "");
    cleaned = cleaned.replace(/\bCopy\s*$/gm, "");
    cleaned = cleaned.replace(/^\s*Copy\s*$/gm, "");

    // 0d. Remove "Use code with caution" Gemini warning
    cleaned = cleaned.replace(/Use code with caution\.?\s*/g, "");

    // 0e. Remove "Download" button text and Gemini Web UI fragments
    cleaned = cleaned.replace(/\bDownload\b/g, "");
    cleaned = cleaned.replace(/\bShare\b/g, "");
    cleaned = cleaned.replace(/\bRegenerate\b/g, "");
    cleaned = cleaned.replace(/Gemini\s+Upgrade to Google AI Plus\s+Conversation with Gemini/gi, "");
    cleaned = cleaned.replace(/AI_SKILLS\s+TXT/gi, "");
    cleaned = cleaned.replace(/Upgrade to Google AI Plus/gi, "");
    cleaned = cleaned.replace(/Conversation with Gemini/gi, "");

    // 1. Remove Protocol Headers & Identity Blocks
    // Bulk removal: eat the entire injected header from [SOURCE...] down to INPUT:...
    cleaned = cleaned.replace(/\[SOURCE:[\s\S]*?INPUT:[^\n]*/gi, "");

    // Strip BANE-V3 reference injection tags
    cleaned = cleaned.replace(/\[MANDATORY RULES\] MANDATORY_RULES\.txt\s*/gi, "");
    cleaned = cleaned.replace(/\[DEPLOYMENT_GUIDE\] AUTONOMOUS_DEPLOYMENT_GUIDE\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[MCP_TOOL_GUIDE\] MCP_TOOLS_DOCUMENTATION\.md\s*/gi, "");
    cleaned = cleaned.replace(/\[EXECUTION COMMAND\]\s*/gi, "");
    cleaned = cleaned.replace(/\[PLATFORM:\s*\w+\]\s*/gi, "");
    cleaned = cleaned.replace(/\[USER_ID:\s*\d+\]\s*/gi, "");

    cleaned = cleaned.replace(/\[PIPELINE:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[TARGET:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[STYLING:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[IDENTITY_PROTOCOL_ACTIVE\][\s\S]*?\[\/IDENTITY_PROTOCOL_ACTIVE\]/gi, "");
    cleaned = cleaned.replace(/\[INSTRUCTION:[\s\S]*?\]/gi, "");

    // Targeted fallbacks for scattered fragments
    cleaned = cleaned.replace(/\[MISSION:[\s\S]*?Wrap in ONE ``` block\./gi, "");
    cleaned = cleaned.replace(/\[MISSION:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[MANDATORY_SYNTAX:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/Use visible literal markdown syntax\.? Wrap in ONE ``` block\./gi, "");
    cleaned = cleaned.replace(/\[IDENTITY:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[SOURCE:[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[CRITICAL INSTRUCTION:[\s\S]*?\]/gi, "");

    // Completely remove the conversation context block and everything inside it
    cleaned = cleaned.replace(/\[CONVERSATION CONTEXT[\s\S]*?\[END CONTEXT\]/gi, "");

    // Fallback if [END CONTEXT] was missing
    cleaned = cleaned.replace(/\[CONVERSATION CONTEXT[\s\S]*?\]/gi, "");
    cleaned = cleaned.replace(/\[END CONTEXT\]/gi, "");
    cleaned = cleaned.replace(/INPUT:[\s\S]*?(\n|$)/gi, "");

    // 2. Remove authorship labels (Gemini said, You said, BANE-NLP said, etc.)
    cleaned = cleaned.replace(/^(Gemini|You|BANE-NLP) said/gmi, "");
    cleaned = cleaned.replace(/\s(Gemini|You|BANE-NLP) said/gi, "");
    cleaned = cleaned.replace(/^\s*said\b/gmi, "");  // Orphaned "said" on its own line
    cleaned = cleaned.replace(/^User:/gmi, "");
    cleaned = cleaned.replace(/^BANE:/gmi, "");

    // 3. Remove ALL citation artifacts (Gemini's various formats)
    // Updated to NOT strip if preceded by a colon (likely a JSON array [0])
    cleaned = cleaned.replace(/\[cite_start\]/gi, "");
    cleaned = cleaned.replace(/\[cite_end\]/gi, "");
    cleaned = cleaned.replace(/\[cite:\s*[\d,\s]+\]/gi, "");   // [cite: 1, 2, 3]
    cleaned = cleaned.replace(/(?<![:"'])\s*\[\d+(?:\s*,\s*\d+)*\]/g, "");  // [1], [1, 2, 3]
    cleaned = cleaned.replace(/\+\d+\b/g, "");                 // +1, +3, etc.

    // 3b. Remove "Analysis Query successful" block
    cleaned = cleaned.replace(/Analysis\s*\n\s*Query successful/gi, "");
    cleaned = cleaned.replace(/Analysis\s*\|\s*Query successful/gi, "");

    // 3c. Remove standalone "Sources" labels
    cleaned = cleaned.replace(/^\s*Sources\s*$/gmi, "");
    cleaned = cleaned.replace(/\bSources\b/gi, "");
    cleaned = cleaned.replace(/Sources\s*/g, "");

    // 4. Protect design: Removed the spacing replacement to ensure Python indentation isn't destroyed


    // 5. Final cleanup of leading/trailing junk
    cleaned = cleaned.trim();

    // CRITICAL: Only reject if it's EXTREMELY obvious placeholder
    // DO NOT reject responses that contain normal words like "analysis"
    const lower = cleaned.toLowerCase();

    // Only reject if it matches EXACTLY these isolated single-word placeholders
    // with no markdown, headers, or structure (which would indicate real content)
    const isSuspiciousSingleWord =
      /^(loading|thinking|generating|creating|working)\.{0,3}$/i.test(cleaned) &&
      cleaned.length < 30;

    // Also reject if it's ONLY repeated UI words
    const isRepeatedUIWord =
      /^(copy|download|share|regenerate|delete|save)\s+(copy|download|share|regenerate|delete|save)$/i.test(cleaned);

    if (isSuspiciousSingleWord || isRepeatedUIWord) {
      return "";
    }

    return cleaned.trim();
  }

  // ─── Send Response Back ─────────────────────────────────────
  function sendResponse(requestId, text, images = [], status = "finished") {
    const responsePayload = {
      pipeline: PIPELINE_NAME,
      id: requestId,
      type: "response",
      source: "gemini",
      status: status,
      timestamp: new Date().toISOString(),
      payload: {
        text: text,
        images: images // Array of URLs or Base64 strings
      },
    };

    window.dispatchEvent(
      new CustomEvent("bnp-response", { detail: responsePayload })
    );

    if (status === "finished") {
      isProcessingPrompt = false;
      setTimeout(processNextPrompt, 100); // brief delay before taking next one
    }
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
      await delay(100);
    }
    return null;
  }

  console.log("[BNP Gemini] Content script ready");
})();
