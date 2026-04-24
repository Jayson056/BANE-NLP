import requests
import os
import sys
# Add parent dir to path to import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import config
from mcp.decorators import mcp_tool

@mcp_tool(name="messenger_v2.send_screenshot", description="Sends a screenshot to Messenger using the Graph API.")
def send_screenshot(file_path: str, recipient_id: str = "26917714517832064"):
    """Sends a screenshot to Messenger using the Graph API."""
    token = getattr(config, "MESSENGER_ACCESS_TOKEN", None)
    if not token:
        return "Error: Messenger token missing in config."
        
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={token}"
    
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