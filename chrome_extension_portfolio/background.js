/**
 * BNP Background Service Worker — v1.2.0
 * ========================================
 * Owns the WebSocket connection to Bane Core (Python).
 * Runs persistently regardless of Chrome window visibility.
 *
 * KEY DESIGN:
 *   - WebSocket lives HERE (not in content scripts)
 *   - chrome.alarms keeps this worker alive every 20s (prevents MV3 30s idle kill)
 *   - chrome.scripting.executeScript() injects prompts into tabs regardless of focus
 *   - Content scripts only do DOM work and relay responses back here via sendMessage
 *
 * This makes injection work even when Chrome is:
 *   - Minimized
 *   - Covered by other applications
 *   - In the background
 */

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────
const WS_URL = "ws://127.0.0.1:8766";
const PIPELINE_NAME = "BNP_PORTFOLIO";
const KEEP_ALIVE_ALARM = "bnp_keepalive";
const RECONNECT_MIN_MS = 1000;   // V2: Faster reconnect (was 3000)
const RECONNECT_MAX_MS = 30000;

// ── State ──────────────────────────────────────────────────────────────────
let ws = null;
let wsReady = false;
let reconnectDelay = RECONNECT_MIN_MS;
let reconnectTimer = null;
let cachedProfileName = "Default";

// Map: messageId → { resolve, reject, timer }
const pendingResponses = new Map();

// Map: tabId → { target, url, timestamp }
const connectedTabs = new Map();

// ── Keep-Alive via chrome.alarms ────────────────────────────────────────────
// Chrome MV3 kills service workers after ~30s idle.
// We create a repeating alarm every 20s to wake the worker and ping the WS.
chrome.alarms.create(KEEP_ALIVE_ALARM, { periodInMinutes: 1 / 4 }); // V2: Every 15s (was 20s)

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEP_ALIVE_ALARM) {
    // Ping the WebSocket to keep it alive
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({
          pipeline: PIPELINE_NAME,
          type: "ping",
          id: crypto.randomUUID(),
          payload: { timestamp: Date.now() }
        }));
      } catch (e) {
        console.warn("[BNP BG] Keep-alive ping failed:", e.message);
      }
    } else if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      // Not connected — attempt reconnect
      console.log("[BNP BG] Keep-alive: WS not open, attempting reconnect...");
      scheduleReconnect(0);
    }
  }
});

// ── Chrome Profile Detection ─────────────────────────────────────────────────
async function detectChromeProfile() {
  const stored = await chrome.storage.local.get("bnp_chrome_profile");
  if (stored.bnp_chrome_profile) {
    cachedProfileName = stored.bnp_chrome_profile;
    return cachedProfileName;
  }
  try {
    const info = await chrome.identity.getProfileUserInfo({ accountStatus: "ANY" });
    if (info && info.email) {
      cachedProfileName = info.email;
      await chrome.storage.local.set({ bnp_chrome_profile: cachedProfileName });
    }
  } catch (e) {
    console.warn("[BNP BG] identity.getProfileUserInfo unavailable:", e);
  }
  return cachedProfileName;
}

// Run profile detection at startup
detectChromeProfile();

// ── WebSocket Management ────────────────────────────────────────────────────
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  console.log(`[BNP BG] Connecting WebSocket to ${WS_URL}...`);
  ws = new WebSocket(WS_URL);

  ws.onopen = async () => {
    wsReady = true;
    reconnectDelay = RECONNECT_MIN_MS;
    console.log("[BNP BG] ✅ WebSocket connected to Bane Core");

    const profile = await detectChromeProfile();

    // Send status immediately so the Python bridge can register this connection
    ws.send(JSON.stringify({
      pipeline: PIPELINE_NAME,
      type: "status",
      id: crypto.randomUUID(),
      payload: {
        status: "connected",
        url: "background://service-worker",
        target: "background",
        chrome_profile: profile,
      }
    }));

    // Broadcast our current tab inventory to the bridge
    await reportConnectedTabs();
  };

  ws.onmessage = async (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (e) {
      console.error("[BNP BG] Failed to parse WS message:", e);
      return;
    }

    if (data.pipeline !== PIPELINE_NAME) return;

    if (data.type === "prompt") {
      console.log("[BNP BG] Prompt received for target:", data.target, "→ dispatching to tab");
      await dispatchPromptToTab(data);
    } else if (data.type === "signal") {
      const action = data.payload?.action;
      const targetName = data.target;
      console.log("[BNP BG] Signal received:", action, "for", targetName);
      await dispatchSignalToTab(data);
    } else if (data.type === "get_axtree") {
      // V2 Phase 4: CDP Accessibility Tree extraction
      const targetTabId = data.payload?.tabId;
      console.log("[BNP BG] AxTree request for tab:", targetTabId);
      try {
        if (typeof getAxTree === "function" && targetTabId) {
          const tree = await getAxTree(targetTabId);
          ws.send(JSON.stringify({
            pipeline: PIPELINE_NAME,
            type: "axtree_response",
            id: data.id,
            payload: { tree: tree, tabId: targetTabId }
          }));
        } else {
          ws.send(JSON.stringify({
            pipeline: PIPELINE_NAME,
            type: "axtree_response",
            id: data.id,
            payload: { tree: "[AxTree extractor not loaded or no tabId]", tabId: targetTabId }
          }));
        }
      } catch (e) {
        console.error("[BNP BG] AxTree extraction failed:", e);
        ws.send(JSON.stringify({
          pipeline: PIPELINE_NAME,
          type: "axtree_response",
          id: data.id,
          payload: { tree: `[AxTree Error: ${e.message}]`, tabId: targetTabId }
        }));
      }
    } else if (data.type === "pong") {
      // Server acknowledged our ping — all good
    }
  };

  ws.onclose = (event) => {
    wsReady = false;
    console.log(`[BNP BG] WebSocket disconnected (code: ${event.code}). Reconnecting in ${reconnectDelay / 1000}s...`);
    scheduleReconnect(reconnectDelay);
    // Reject all pending responses
    pendingResponses.forEach(({ reject, timer }, msgId) => {
      clearTimeout(timer);
      reject(new Error("WebSocket disconnected"));
      pendingResponses.delete(msgId);
    });
  };

  ws.onerror = (error) => {
    console.error("[BNP BG] WebSocket error:", error);
  };
}

function scheduleReconnect(delayMs) {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
    reconnectDelay = Math.min(reconnectDelay * 1.5, RECONNECT_MAX_MS);
  }, delayMs);
}

// ── Tab Inventory ────────────────────────────────────────────────────────────
function detectTargetFromUrl(url) {
  if (!url) return null;
  
  // ── Auto Profile Identification ──
  // If the URL contains ?bnp_profile=Profile+X, we adopt that identity
  try {
    const urlObj = new URL(url);
    const bnpProfile = urlObj.searchParams.get("bnp_profile");
    if (bnpProfile && bnpProfile !== cachedProfileName) {
      console.log(`[BNP BG] 🆕 Auto-identifying as: ${bnpProfile}`);
      cachedProfileName = bnpProfile;
      chrome.storage.local.set({ bnp_chrome_profile: bnpProfile });
      // WS will naturally report the new profile on next status ping or reconnection
    }
  } catch (e) {}

  if (url.includes("gemini.google.com")) return "gemini_portfolio";
  if (url.includes("notebooklm.google.com")) return "notebooklm";
  if (url.includes("chatgpt.com")) return "chatgpt";
  return null;
}

async function reportConnectedTabs() {
  if (!wsReady) return;
  const profile = cachedProfileName;

  try {
    const tabs = await chrome.tabs.query({ url: [
      "https://gemini.google.com/*",
      "https://notebooklm.google.com/*",
      "https://chatgpt.com/*"
    ]});

    for (const tab of tabs) {
      const target = detectTargetFromUrl(tab.url);
      if (!target) continue;

      connectedTabs.set(tab.id, { target, url: tab.url, timestamp: Date.now() });

      ws.send(JSON.stringify({
        pipeline: PIPELINE_NAME,
        type: "status",
        id: crypto.randomUUID(),
        payload: {
          status: "tab_connected",
          target,
          chrome_profile: profile,
          url: tab.url,
          tab_id: tab.id,
        }
      }));
      console.log(`[BNP BG] Reported tab: [${tab.id}] ${target} @ ${profile}`);
    }
  } catch (e) {
    console.warn("[BNP BG] reportConnectedTabs error:", e.message);
  }
}

// ── Prompt Dispatch to Tab (works even when minimized) ────────────────────────
async function dispatchPromptToTab(payload) {
  // Portfolio extension: use target as-is (gemini_portfolio), no stripping
  const targetName = payload.target || "gemini_portfolio";

  // Find the best matching tab for this target
  let targetTabId = null;

  // First: check our connectedTabs registry
  for (const [tabId, info] of connectedTabs) {
    if (info.target === targetName) {
      targetTabId = tabId;
    }
  }

  // Fallback: query tabs directly (catches tabs opened before this worker started)
  if (!targetTabId) {
    const urlPatterns = {
      gemini_portfolio: "https://gemini.google.com/*",
      gemini: "https://gemini.google.com/*",
      notebooklm: "https://notebooklm.google.com/*",
      chatgpt: "https://chatgpt.com/*",
    };
    const pattern = urlPatterns[targetName];
    if (pattern) {
      try {
        const tabs = await chrome.tabs.query({ url: pattern });
        if (tabs.length > 0) {
          // Prefer the most recently active tab
          const sorted = tabs.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
          targetTabId = sorted[0].id;
          connectedTabs.set(targetTabId, { target: targetName, url: sorted[0].url, timestamp: Date.now() });
          console.log(`[BNP BG] Discovered target tab via query: [${targetTabId}] ${targetName}`);
        }
      } catch (e) {
        console.warn("[BNP BG] Tab query failed:", e.message);
      }
    }
  }

  if (!targetTabId) {
    console.error(`[BNP BG] No tab found for target '${targetName}'`);
    sendErrorResponse(payload.id, `No ${targetName} tab open in Chrome.`);
    return;
  }

  try {
    // chrome.scripting.executeScript injects into the tab even if it's minimized.
    // We pass the payload as a serialized arg — it runs in the ISOLATED world
    // where our content script already lives.
    await chrome.scripting.executeScript({
      target: { tabId: targetTabId },
      world: "ISOLATED",
      func: (payloadStr) => {
        // This runs inside the tab's ISOLATED world (same as content script)
        const payload = JSON.parse(payloadStr);
        window.dispatchEvent(new CustomEvent("bnp-prompt", { detail: payload }));
      },
      args: [JSON.stringify(payload)],
    });
    console.log(`[BNP BG] Prompt injected into tab [${targetTabId}] via executeScript`);
  } catch (e) {
    console.error(`[BNP BG] executeScript failed for tab [${targetTabId}]:`, e.message);

    // The content script might not be loaded yet — try injecting it first
    if (e.message && e.message.includes("Cannot access")) {
      console.warn("[BNP BG] Tab may not have content script — attempting re-injection of scripts...");
      try {
        const scriptFiles = getContentScriptFiles(targetName);
        if (scriptFiles.length > 0) {
          await chrome.scripting.executeScript({
            target: { tabId: targetTabId },
            files: scriptFiles,
          });
          // Retry the prompt injection
          await chrome.scripting.executeScript({
            target: { tabId: targetTabId },
            world: "ISOLATED",
            func: (payloadStr) => {
              const payload = JSON.parse(payloadStr);
              window.dispatchEvent(new CustomEvent("bnp-prompt", { detail: payload }));
            },
            args: [JSON.stringify(payload)],
          });
          console.log(`[BNP BG] Retry injection succeeded for tab [${targetTabId}]`);
        }
      } catch (e2) {
        console.error(`[BNP BG] Retry injection also failed:`, e2.message);
        sendErrorResponse(payload.id, `Injection failed: ${e2.message}`);
      }
    } else {
      sendErrorResponse(payload.id, `Injection failed: ${e.message}`);
    }
  }
}

function getContentScriptFiles(target) {
  const map = {
    gemini: ["websocket_bridge.js", "content_gemini.js"],
    gemini_portfolio: ["websocket_bridge.js", "content_gemini.js"],
    notebooklm: ["websocket_bridge.js", "content_notebooklm.js"],
    chatgpt: ["websocket_bridge.js", "content_chatgpt.js"],
  };
  return map[target] || [];
}

async function dispatchSignalToTab(payload) {
  const targetName = payload.target || "gemini_portfolio";
  let targetTabId = null;

  for (const [tabId, info] of connectedTabs) {
    if (info.target === targetName) targetTabId = tabId;
  }
  if (!targetTabId) return;

  try {
    await chrome.scripting.executeScript({
      target: { tabId: targetTabId },
      world: "ISOLATED",
      func: (payloadStr) => {
        const p = JSON.parse(payloadStr);
        if (p.payload?.action === "navigate" && p.payload?.url) {
          window.location.href = p.payload.url;
        } else {
          window.dispatchEvent(new CustomEvent("bnp-signal", { detail: p.payload }));
        }
      },
      args: [JSON.stringify(payload)],
    });
  } catch (e) {
    console.warn("[BNP BG] Signal dispatch failed:", e.message);
  }
}

// ── Send Responses Back to BANE Core ────────────────────────────────────────
function sendResponseToServer(responsePayload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(responsePayload));
    console.log(`[BNP BG] Response relayed to Bane Core (id: ${responsePayload.id})`);
  } else {
    console.warn("[BNP BG] Cannot relay response — WS not open. Reconnecting...");
    scheduleReconnect(0);
  }
}

function sendErrorResponse(msgId, errorText) {
  sendResponseToServer({
    pipeline: PIPELINE_NAME,
    type: "response",
    id: msgId,
    status: "error",
    payload: { text: `❌ ${errorText}`, images: [] }
  });
}

// ── Messages from Content Scripts ────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  // ── Profile Management ──
  if (message.type === "BNP_GET_PROFILE") {
    detectChromeProfile().then(profile => sendResponse({ profile }));
    return true;
  }
  if (message.type === "BNP_SET_PROFILE") {
    cachedProfileName = message.profile || "Default";
    chrome.storage.local.set({ bnp_chrome_profile: cachedProfileName });
    sendResponse({ status: "ok", profile: cachedProfileName });
    return true;
  }

  // ── Tab Registration ──
  if (message.type === "BNP_CONTENT_READY") {
    connectedTabs.set(tabId, {
      target: message.target,
      url: sender.tab.url,
      timestamp: Date.now(),
    });
    console.log(`[BNP BG] Content script ready on tab [${tabId}] for ${message.target}`);

    // Inform Python bridge that this tab/target is now live
    if (wsReady) {
      ws.send(JSON.stringify({
        pipeline: PIPELINE_NAME,
        type: "status",
        id: crypto.randomUUID(),
        payload: {
          status: "connected",
          target: message.target,
          chrome_profile: cachedProfileName,
          url: sender.tab.url,
          tab_id: tabId,
        }
      }));
    }
    sendResponse({ status: "acknowledged" });
    return true;
  }

  if (message.type === "BNP_CONTENT_DISCONNECT") {
    connectedTabs.delete(tabId);
    console.log(`[BNP BG] Content script disconnected from tab [${tabId}]`);
    sendResponse({ status: "acknowledged" });
    return true;
  }

  // ── Response Relay (CRITICAL: content script → background → Python) ──
  // Content scripts can't send over WebSocket directly when BG worker owns it.
  // They send responses here, and we forward over the WS.
  if (message.type === "BNP_RESPONSE") {
    console.log(`[BNP BG] Response received from content script (id: ${message.payload?.id})`);
    sendResponseToServer(message.payload);
    sendResponse({ status: "relayed" });
    return true;
  }

  // ── Log Relay ──
  if (message.type === "BNP_LOG") {
    console.log(`[BNP/${message.source}]`, message.text);
    if (wsReady && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        pipeline: PIPELINE_NAME,
        type: "log",
        id: crypto.randomUUID(),
        payload: { source: message.source, text: message.text }
      }));
    }
    sendResponse({ status: "logged" });
    return true;
  }

  // ── Image Fetch Proxies (unchanged) ──
  if (message.type === "BNP_FETCH_IMAGE") {
    const blobToDataUrl = async (blob) => {
      const buffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      const CHUNK = 8192;
      let binary = "";
      for (let i = 0; i < bytes.byteLength; i += CHUNK) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
      }
      return `data:${blob.type || "image/png"};base64,${btoa(binary)}`;
    };

    fetch(message.url, { credentials: "include" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
      .then(async blob => sendResponse({ dataUrl: await blobToDataUrl(blob) }))
      .catch(() =>
        fetch(message.url, { mode: "cors", credentials: "omit" })
          .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
          .then(async blob => sendResponse({ dataUrl: await blobToDataUrl(blob) }))
          .catch(e2 => sendResponse({ error: e2.message }))
      );
    return true;
  }

  if (message.type === "BNP_FETCH_IMAGE_MAIN_WORLD") {
    chrome.downloads.download({
      url: message.url,
      saveAs: false,
      conflictAction: "uniquify",
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        sendResponse({ error: chrome.runtime.lastError.message });
        return;
      }
      const listener = (delta) => {
        if (delta.id === downloadId && delta.state?.current === "complete") {
          chrome.downloads.onChanged.removeListener(listener);
          chrome.downloads.search({ id: downloadId }, (results) => {
            if (results && results.length > 0) {
              sendResponse({ dataUrl: "bnp-local-file:" + results[0].filename });
            } else {
              sendResponse({ error: "Downloaded file not found" });
            }
          });
        } else if (delta.id === downloadId && delta.state?.current === "interrupted") {
          chrome.downloads.onChanged.removeListener(listener);
          sendResponse({ error: "Download interrupted" });
        }
      };
      chrome.downloads.onChanged.addListener(listener);
    });
    return true;
  }

  return false;
});

// ── Tab Lifecycle ─────────────────────────────────────────────────────────────
chrome.tabs.onRemoved.addListener((tabId) => {
  if (connectedTabs.has(tabId)) {
    const info = connectedTabs.get(tabId);
    connectedTabs.delete(tabId);
    console.log(`[BNP BG] Tab [${tabId}] (${info.target}) closed`);
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url) {
    const target = detectTargetFromUrl(tab.url);
    if (target) {
      connectedTabs.set(tabId, { target, url: tab.url, timestamp: Date.now() });
      console.log(`[BNP BG] Tab [${tabId}] updated: ${target}`);
    }
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────
connectWebSocket();
console.log("[BNP BG] Background service worker v1.2.0 started — WebSocket owned by background.");
