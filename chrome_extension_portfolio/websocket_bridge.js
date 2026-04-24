/**
 * BNP WebSocket Bridge — v1.2.0
 * ================================
 * NOTE: The WebSocket connection now lives in background.js (service worker).
 * This file's job is:
 *   1. Listen for BNP_INJECT messages from background.js (via chrome.runtime.onMessage)
 *   2. Dispatch them as bnp-prompt / bnp-signal CustomEvents to content scripts
 *   3. Listen for bnp-response events from content scripts and relay to background.js
 *
 * WHY: Content scripts are throttled/suspended when Chrome is minimized.
 *      The background service worker (background.js) is NOT throttled and owns
 *      the persistent WebSocket. It uses chrome.scripting.executeScript() to
 *      wake this content script on demand even when Chrome is hidden.
 */

(function () {
  "use strict";

  // Guard: prevent double-injection if executeScript runs multiple times
  if (window.__BNP_BRIDGE_ACTIVE) {
    console.log("[BNP Bridge] Already active — skipping re-init.");
    return;
  }
  window.__BNP_BRIDGE_ACTIVE = true;

  const PIPELINE_NAME = "BNP_PORTFOLIO";

  console.log("[BNP Bridge] v1.2.0 — Relay-only mode (WS owned by background.js)");

  // ── Notify background that content script is ready ────────────────────────
  chrome.runtime.sendMessage({
    type: "BNP_CONTENT_READY",
    target: detectTarget(),
  }, (resp) => {
    void chrome.runtime.lastError; // suppress channel-closed noise
    console.log("[BNP Bridge] Registered with background:", resp?.status || "no response");
  });

  // ── Target Detection ────────────────────────────────────────────────────────
  function detectTarget() {
    const url = window.location.href;
    if (url.includes("gemini.google.com")) return "gemini_portfolio";
    if (url.includes("notebooklm.google.com")) return "notebooklm";
    if (url.includes("chatgpt.com")) return "chatgpt";
    return "unknown";
  }

  // ── Dispatch BNP events to content scripts ──────────────────────────────────
  function dispatchBNPPrompt(payload) {
    window.dispatchEvent(new CustomEvent("bnp-prompt", { detail: payload }));
  }

  function dispatchBNPSignal(payload) {
    window.dispatchEvent(new CustomEvent("bnp-signal", { detail: payload }));
  }

  // ── Relay: background.js → content script ──────────────────────────────────
  // background.js uses chrome.scripting.executeScript to inject an event directly,
  // but we also handle the runtime message path as a fallback.
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "BNP_INJECT_PROMPT") {
      console.log("[BNP Bridge] Prompt received from background:", message.payload?.payload?.message?.substring(0, 60));
      dispatchBNPPrompt(message.payload);
      sendResponse({ status: "dispatched" });
      return true;
    }
    if (message.type === "BNP_INJECT_SIGNAL") {
      console.log("[BNP Bridge] Signal received from background:", message.payload?.action);
      dispatchBNPSignal(message.payload);
      sendResponse({ status: "dispatched" });
      return true;
    }
    return false;
  });

  // ── Relay: content script → background.js → Python WebSocket ───────────────
  window.addEventListener("bnp-response", (event) => {
    const responsePayload = event.detail;
    console.log("[BNP Bridge] Relaying response to background (id:", responsePayload?.id, ")");
    chrome.runtime.sendMessage({ type: "BNP_RESPONSE", payload: responsePayload }, (resp) => {
      void chrome.runtime.lastError;
    });
  });

  // ── Log relay ───────────────────────────────────────────────────────────────
  window.addEventListener("bnp-log", (event) => {
    chrome.runtime.sendMessage({
      type: "BNP_LOG",
      source: event.detail?.source || "Content",
      text: event.detail?.text || "",
    }, () => { void chrome.runtime.lastError; });
  });

  // ── Expose status ───────────────────────────────────────────────────────────
  window.__BNP_BRIDGE = {
    isConnected: () => true, // Always "connected" — real WS is in background.js
    version: "1.2.0",
    mode: "background-owned-ws",
  };

  console.log("[BNP Bridge] Ready. Prompt dispatch: background → executeScript → here → content script");
})();
