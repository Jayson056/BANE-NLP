# BANE-NLP Speed & Polling Optimization Plan

The goal is to eliminate artificial delays, reduce sleep intervals, and increase the polling frequency across the entire architecture. This will make the AI loop respond much faster.

## User Review Required

Please review the proposed speed optimizations. 

> [!WARNING]
> Making the intervals *too* fast can sometimes trigger rate limits (e.g., from Telegram or Gemini) or cause DOM race conditions in the browser. I have selected aggressive but safe values.

## Proposed Changes

### 1. `chrome_extension/content_gemini.js`
*Reduces the delay before the extension processes the next prompt in the queue.*
- Change `setTimeout(processNextPrompt, 500)` to `setTimeout(processNextPrompt, 100)`
- Reduce `greedDelay` and UI sync delays from `300ms` down to `100ms` or `50ms`.

### 2. `core/browser_bridge.py`
*Optimizes the WebSocket ping/pong and queue loop.*
- If there are `asyncio.sleep()` calls in the event loop, reduce them to `0.05` seconds to ensure instant dispatch.

### 3. `pipeline/daemon.py` (if applicable)
*Reduces background polling.*
- Change `self.POLL_INTERVAL_MS = 1000` (or similar) to `200` to process tasks 5x faster.

### 4. `pipeline/engine.py` & `pipeline/composer.py`
*Optimizes the autonomous loop.*
- Reduce inter-loop delays so the AI immediately starts the next tool action without waiting 1-2 seconds.

## Open Questions
- Is it okay if the AI responds *so* fast that you might see intermediate tool result messages (like `[Tool executed]`) rapidly spamming before the final response?

## Verification Plan
After applying these changes, I will restart the BANE engine and you will need to refresh your Gemini tab. We can then test a multi-step task to verify the speed improvement.
