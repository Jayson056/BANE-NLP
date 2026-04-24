import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool

import requests
import os
import sys

# Ensure root is in path to find config
sys.path.append(os.getcwd())
import config

def send_telegram_document(file_path: str, user_id: str = None, caption: str = ""):
    """Sends a file to Telegram using the bot API."""
    token = getattr(config, 'TELEGRAM_TOKEN', None)
    # The authorized ID from mandatory rules
    chat_id = user_id if user_id else "5662168844"
    
    if not os.path.exists(file_path):
        return f"❌ Error: File {file_path} not found."

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with open(file_path, 'rb') as doc:
            files = {'document': doc}
            data = {'chat_id': chat_id, 'caption': caption}
            res = requests.post(url, data=data, files=files)
            res.raise_for_status()
            return f"✅ File {os.path.basename(file_path)} sent successfully."
    except Exception as e:
        return f"❌ Failed to send {os.path.basename(file_path)}: {str(e)}"