"""
BNP Response Handler
=====================
Processes AI responses received from the browser bridge.
"""

from core.logger import log_event, log_error, log_conversation


class ResponseHandler:
    """Handles AI responses coming back through the pipeline."""

    def __init__(self):
        self._pending_callbacks: dict[str, callable] = {}

    def register_callback(self, request_id: str, callback: callable) -> None:
        """Register a callback for when a specific request's response arrives."""
        self._pending_callbacks[request_id] = callback
        log_event("RESPONSE", f"Callback registered for request {request_id}")

    async def handle_response(self, response_payload: dict) -> str | None:
        """
        Process an AI response payload.

        Args:
            response_payload: The BNP response dict from the browser.

        Returns:
            The AI response text, or None if invalid.
        """
        try:
            msg_type = response_payload.get("type")
            if msg_type != "response":
                log_event("RESPONSE", f"Ignoring non-response payload type: {msg_type}")
                return None

            source = response_payload.get("source", "unknown")
            inner = response_payload.get("payload", {})
            text = inner.get("text", "")

            if not text:
                log_event("RESPONSE", "Empty response text received")
                return None
            
            # Sanitize response
            text = self._sanitize_text(text)

            log_event("RESPONSE", f"AI response received from {source} ({len(text)} chars)")
            return text

        except Exception as e:
            log_error("RESPONSE", e)
            return None

    def _sanitize_text(self, text: str) -> str:
        """Remove AI artifacts and enforce formatting rules."""
        if not text:
            return ""
            
        # 0. DEEP FIX: Unescape literal '\n' and '\t' sequences if they were captured as text
        # Many LLMs output these when they are "constrained" or when the browser bridge captures
        # the text of a code block literally.
        if "call_tool" in text and ("\\n" in text or "\\t" in text):
            # This is specifically for code strings in JSON tool calls
            # We must be careful not to break valid JSON escaping, so we only target 
            # sequences that cause Python/Script syntax errors.
            text = text.replace("\\n", "\n").replace("\\t", "    ")

        # 1. Remove "Markdown" prefix that Gemini web UI sometimes includes in copy-paste
        import re
        text = re.sub(r'^(markdown|Markdown)\s*', '', text)

        # 2. Trim whitespace
        text = text.strip()
        return text

    def extract_text(self, response_payload: dict) -> str:
        """
        Extract the text from a response payload, preserving the full Gemini answer (explanation, code, context).
        Only remove suggestions if they are clearly separated by a header (e.g., 'Suggested Questions:').
        """
        try:
            inner = response_payload.get("payload", {})
            text = inner.get("text", "")
            import re
            # Only strip suggestions if they are separated by a clear header
            suggestion_match = re.search(r'\n*Suggested Questions?:\s*(.*?)$', text, flags=re.IGNORECASE | re.DOTALL)
            if suggestion_match:
                text = text[:suggestion_match.start()]
            # Otherwise, do NOT strip anything—preserve full answer (explanation, code, etc.)
            return self._sanitize_text(text)
        except (AttributeError, TypeError):
            return ""

    def extract_suggestions(self, response_payload: dict) -> list[str]:
        """Extract suggested follow-up queries (buttons) with smart text fallback."""
        try:
            inner = response_payload.get("payload", {})
            dom_suggestions = inner.get("suggestions", [])
            
            # --- Smart Detection: Extract from raw text if DOM pills didn't load ---
            text = inner.get("text", "")
            import re
            text_suggestions = []
            
            suggestion_match = re.search(r'\n*Suggested Questions?:\s*(.*?)$', text, flags=re.IGNORECASE | re.DOTALL)
            if suggestion_match:
                raw_list = suggestion_match.group(1).split('\n')
                text_suggestions = [q.strip().strip('-•*1234567890. ') for q in raw_list if q.strip()]
            else:
                # Implicit extraction: trailing questions
                lines = text.strip().split('\n')
                for i in range(len(lines)-1, -1, -1):
                    line = lines[i].strip()
                    if line and line.endswith('?') and len(line) < 120:
                        text_suggestions.insert(0, line) # Add to front to maintain order
                    elif line == "":
                        continue
                    else:
                        break
                        
            # --- Process and clean up ALL suggestions (DOM + Text) ---
            seen = set()
            final_suggestions = []
            
            # Combine whatever we found
            merged = dom_suggestions + text_suggestions
            
            for s in merged:
                if not s: continue
                # Split squashed inline arrows if present (e.g. "→ Q1? → Q2?")
                if ' → ' in s:
                    parts = s.split(' → ')
                else:
                    parts = [s]
                
                for p in parts:
                    # Strip bullet points, numbers, arrows, and extra whitespace
                    clean_p = re.sub(r'^[→•\-\*\d\.\s]+', '', p).strip()
                    if clean_p and clean_p not in seen:
                        seen.add(clean_p)
                        final_suggestions.append(clean_p)
                        
            return final_suggestions
        except (AttributeError, TypeError):
            return []

