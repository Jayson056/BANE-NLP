import requests
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

from mcp_registry import mcp_tool

@mcp_tool
def messenger_send_screenshot(file_path: str):
    """Sends a screenshot from the local workspace to the Messenger user via Facebook Graph API."""
    access_token = getattr(config, "MESSENGER_PAGE_ACCESS_TOKEN", None)
    if not access_token:
        return "Error: Messenger token missing in config."
    recipient_id = "26917714517832064"
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={access_token}"
    
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found."

    try:
        with open(file_path, 'rb') as f:
            files = {
                'filedata': (os.path.basename(file_path), f, 'image/png')
            }
            data = {
                'recipient': '{"id": "' + recipient_id + '"}',
                'message': '{"attachment": {"type": "image", "payload": {}}}'
            }
            response = requests.post(url, files=files, data=data)
            res_json = response.json()
            
            if response.status_code == 200:
                return "Successfully sent screenshot to Messenger."
            else:
                return f"Failed to send: {res_json}"
    except Exception as e:
        return f"API Error: {str(e)}"