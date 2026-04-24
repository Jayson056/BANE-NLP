import re
from typing import List, Dict, Any

class TelegramFormatter:
    """
    Converts standard Markdown (including tables) into Telegram-compatible HTML.
    Optimizes layout for mobile readability.
    """

    @staticmethod
    def format_message(text: str) -> str:
        if not text:
            return "", []

        # 0. Extract buttons (e.g. [Label](data)) before formatting
        buttons = []
        
        # Pattern 1: [Label](callback_data)
        btn_matches = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text)
        for label, data in btn_matches:
            if not data.startswith(('http', 'www')):
                # TRUNCATE to 64 bytes to prevent Button_data_invalid
                safe_data = data[:64]
                buttons.append({"label": label, "data": safe_data})
                text = text.replace(f"[{label}]({data})", "")
        
        # Pattern 2: [Export to Sheets] (special case)
        if "Export to Sheets" in text:
            if not any(b["label"] == "📊 Export to Sheets" for b in buttons):
                buttons.append({"label": "📊 Export to Sheets", "data": "export_sheets"})
            text = text.replace("Export to Sheets", "")

        # 1. Pre-process malformed Bold/Italic like *_text_* or _*text*_
        # These are common in AI outputs but Telegram hates them.
        text = re.sub(r'\*_(.*?)_\*', r'<b><i>\1</i></b>', text)
        text = re.sub(r'_\*(.*?)\*_', r'<i><b>\1</b></i>', text)

        # 2. Handle Markdown Tables
        text = TelegramFormatter._convert_tables(text)

        # 3. Convert standard Markdown to HTML
        # Bold
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        # Italic (careful with underscores in code)
        text = re.sub(r'(?<!\\)_(.*?)_', r'<i>\1</i>', text)
        
        # Code blocks (triple backticks)
        text = re.sub(r'```(?:[a-zA-Z]*)\n?(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
        
        # Inline code (single backtick)
        text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

        # 4. Clean up extra newlines
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        return text, buttons

    @staticmethod
    def _convert_tables(text: str) -> str:
        lines = text.split('\n')
        result = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Robust table detection:
            # Look for lines with at least 2 pipes, or the specific header pattern from the user screenshot
            is_table_start = (
                (line.count('|') >= 2) and 
                i + 1 < len(lines) and 
                (lines[i+1].count('|') >= 2 and ('-' in lines[i+1] or ':' in lines[i+1]))
            )
            
            # Fallback for "jumbled" tables that might have lost pipes but kept structure
            # (e.g. if a previous sanitizer stripped them but kept lines)
            if not is_table_start and "Category" in line and "Item" in line and "Description" in line:
                # This matches the user's specific "jumbled" header
                is_table_start = True

            if is_table_start:
                table_lines = []
                # Headers
                if '|' in line:
                    headers = [h.strip() for h in line.split('|') if h.strip()]
                else:
                    # Heuristic for jumbled header: "CategoryItem NameDescription"
                    # Try to split by common words
                    headers = ["Category", "Item", "Description"]
                
                i += 1
                # Skip separator if it exists
                if i < len(lines) and (lines[i].count('|') >= 2 or '---' in lines[i]):
                    i += 1
                
                # Rows
                while i < len(lines):
                    row_line = lines[i].strip()
                    if not row_line: break # End of table
                    
                    if '|' in row_line:
                        cols = [c.strip() for c in row_line.split('|') if c.strip()]
                    else:
                        # Fallback for jumbled row: "__🏠 Core AI__Bane_NLP/..."
                        # Split by double underscores if present
                        if '__' in row_line:
                            cols = [c.strip() for c in row_line.split('__') if c.strip()]
                        else:
                            # Not a table row anymore?
                            break
                    
                    if cols:
                        table_lines.append(cols)
                    i += 1
                
                # Format the collected table
                result.append(TelegramFormatter._render_table_as_cards(headers, table_lines))
            else:
                result.append(lines[i])
                i += 1
        
        return '\n'.join(result)

    @staticmethod
    def _render_table_as_cards(headers: List[str], rows: List[List[str]]) -> str:
        if not rows:
            return ""
        
        card_output = []
        # Add a subtle separator for the table start
        card_output.append("<code>────────────────────────────</code>")
        
        for row in rows:
            # Premium "Card" look
            first_col = row[0] if len(row) > 0 else "Item"
            
            # Use icons for common types if present in first col
            card = f"🔹 <b>{first_col}</b>\n"
            
            for idx in range(1, len(row)):
                header = headers[idx] if idx < len(headers) else "Detail"
                val = row[idx]
                
                # Clean up value
                val = val.strip()
                if not val: continue
                
                # If it looks like a path or code, use code tag
                if '/' in val or '\\' in val or '.' in val or val.endswith('/'):
                    val = f"<code>{val}</code>"
                
                card += f"  ▫️ <i>{header}:</i> {val}\n"
            
            card_output.append(card)
        
        card_output.append("<code>────────────────────────────</code>")
        return "\n".join(card_output)

    @staticmethod
    def escape_html(text: str) -> str:
        """Escapes text for Telegram HTML."""
        if not text: return ""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    @staticmethod
    def finalize_html(text: str) -> str:
        """
        Final pass to ensure valid Telegram HTML.
        We escape everything and then restore only the tags we support.
        """
        # Split by allowed tags to escape only the content between them
        # FIXED: Added the missing '>' to the [biu] part of the regex
        parts = re.split(r'(</?[biu]>|</?code>|</?pre>|</?a>|</?s>)', text, flags=re.IGNORECASE)
        final_parts = []
        for part in parts:
            if re.match(r'</?[biu]>|</?code>|</?pre>|</?a>|</?s>', part, flags=re.IGNORECASE):
                final_parts.append(part.lower())
            else:
                final_parts.append(TelegramFormatter.escape_html(part))
        
        return "".join(final_parts)
