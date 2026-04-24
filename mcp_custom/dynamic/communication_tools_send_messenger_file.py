import os
import sys
# Add parent dir to path to import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import config
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.decorators import mcp_custom_tool
import requests
import json

@mcp_custom_tool(name="communication_tools.send_messenger_file", description="Sends a local image file to Messenger")
def send_messenger_file(file_path: str, recipient_id: str = "26917714517832064"):
    token = getattr(config, "MESSENGER_ACCESS_TOKEN", None)
    if not token:
        return "Error: Messenger token missing in config."
        
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={token}"
    
    payload = {
        'recipient': json.dumps({'id': recipient_id}),
        'message': json.dumps({'attachment': {'type': 'image', 'payload': {'is_reusable': True}}})
    }
    
    with open(file_path, 'rb') as f:
        files = {
            'filedata': (file_path, f, 'image/png')
        }
        response = requests.post(url, data=payload, files=files)
        
    return response.json()