/**
 * BNP AxTree Extractor (V2 Phase 4: Efficiency)
 * ================================================
 * Uses the Chrome DevTools Protocol (CDP) via chrome.debugger to extract
 * the Accessibility Tree from a target tab. This provides a pure semantic
 * map of the page (Roles, Names, States) without DOM noise, yielding
 * up to 10x token reduction compared to raw HTML extraction.
 *
 * Usage from background.js:
 *   import { getAxTree } from './axtree_extractor.js';
 *   const tree = await getAxTree(tabId);
 *
 * Architecture:
 *   1. Attach the debugger to the target tab
 *   2. Call Accessibility.getFullAXTree via CDP
 *   3. Serialize the tree into a compact text format
 *   4. Detach the debugger to release resources
 */

"use strict";

/**
 * Extract the Accessibility Tree from a Chrome tab using CDP.
 * 
 * @param {number} tabId - The Chrome tab ID to extract from.
 * @returns {Promise<string>} Serialized AxTree in compact text format.
 */
async function getAxTree(tabId) {
  const debuggee = { tabId: tabId };

  try {
    // ── 1. Attach debugger ────────────────────────────────────────────────
    await new Promise((resolve, reject) => {
      chrome.debugger.attach(debuggee, "1.3", () => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve();
        }
      });
    });

    // ── 2. Enable Accessibility domain ────────────────────────────────────
    await new Promise((resolve, reject) => {
      chrome.debugger.sendCommand(debuggee, "Accessibility.enable", {}, () => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve();
        }
      });
    });

    // ── 3. Get full Accessibility Tree ────────────────────────────────────
    const result = await new Promise((resolve, reject) => {
      chrome.debugger.sendCommand(debuggee, "Accessibility.getFullAXTree", {}, (res) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(res);
        }
      });
    });

    // ── 4. Serialize to compact text ──────────────────────────────────────
    const nodes = result.nodes || [];
    const serialized = serializeAxTree(nodes);

    return serialized;

  } catch (err) {
    console.error("[BNP AxTree] Error extracting tree:", err.message);
    return `[AxTree Error: ${err.message}]`;

  } finally {
    // ── 5. Always detach debugger ─────────────────────────────────────────
    try {
      await new Promise((resolve) => {
        chrome.debugger.detach(debuggee, () => {
          resolve();
        });
      });
    } catch (e) {
      // Detach may fail if already detached — safe to ignore
    }
  }
}


/**
 * Serialize CDP AXTree nodes into a compact, token-efficient text format.
 * 
 * Format per node:
 *   [depth_indent][Role] Name (State)
 * 
 * Example:
 *   [WebArea] Google Gemini
 *     [navigation] Main menu
 *       [link] Home (focused)
 *       [link] Settings
 *     [main]
 *       [textbox] Enter a prompt (editable, focused)
 *       [button] Send
 * 
 * Filters out ignored/invisible nodes to reduce noise.
 *
 * @param {Array} nodes - Raw CDP AXTree nodes.
 * @returns {string} Compact serialized tree.
 */
function serializeAxTree(nodes) {
  if (!nodes || nodes.length === 0) {
    return "[Empty AxTree]";
  }

  // Build a map of nodeId → node for parent-child traversal
  const nodeMap = new Map();
  for (const node of nodes) {
    nodeMap.set(node.nodeId, node);
  }

  // Roles to skip (noise reducers)
  const IGNORED_ROLES = new Set([
    "none", "generic", "InlineTextBox", "LineBreak",
    "StaticText",  // Only skip if no meaningful name
  ]);

  const lines = [];

  /**
   * Recursively serialize a node and its children.
   */
  function visit(nodeId, depth) {
    const node = nodeMap.get(nodeId);
    if (!node) return;

    const role = node.role?.value || "unknown";
    const name = node.name?.value || "";
    const ignored = node.ignored || false;

    // Skip ignored and noise nodes
    if (ignored) return;
    if (IGNORED_ROLES.has(role) && !name) return;

    // Build state indicators
    const states = [];
    if (node.properties) {
      for (const prop of node.properties) {
        if (prop.name === "focused" && prop.value?.value === true) states.push("focused");
        if (prop.name === "disabled" && prop.value?.value === true) states.push("disabled");
        if (prop.name === "checked" && prop.value?.value === "true") states.push("checked");
        if (prop.name === "expanded" && prop.value?.value === true) states.push("expanded");
        if (prop.name === "editable" && prop.value?.value === "plaintext") states.push("editable");
      }
    }

    // Format: indent + [Role] Name (states)
    const indent = "  ".repeat(depth);
    let line = `${indent}[${role}]`;
    if (name) line += ` ${name}`;
    if (states.length > 0) line += ` (${states.join(", ")})`;

    lines.push(line);

    // Recurse into children
    if (node.childIds) {
      for (const childId of node.childIds) {
        visit(childId, depth + 1);
      }
    }
  }

  // Start from root nodes (nodes without parents, or the first node)
  const rootNode = nodes[0];
  if (rootNode) {
    visit(rootNode.nodeId, 0);
  }

  return lines.join("\n");
}


// Export for use in background.js
if (typeof globalThis !== "undefined") {
  globalThis.getAxTree = getAxTree;
  globalThis.serializeAxTree = serializeAxTree;
}
