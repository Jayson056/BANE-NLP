import os
import sys
# Add parent dir to path to import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import config
from mcp.decorators import mcp_tool

import requests
import subprocess

@mcp_tool(name="messenger.send_screenshot", description="Captures a screenshot and sends it to Messenger.")
def send_screenshot(file_path: str = "D:\\Bane_NLP\\Screenshot\\emp_screenshot.png", recipient_id: str = "26917714517832064"):
    """Captures a screenshot and sends it to Messenger."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Capture screenshot using system tools (assuming Windows environment per diagnostic hints)
    try:
        # Using PowerShell to take a screenshot as a reliable native method
        ps_command = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('%{{PRTSC}}'); $img = [System.Windows.Forms.Clipboard]::GetImage(); $img.Save('{file_path}')"
        subprocess.run(["powershell", "-Command", ps_command], check=True)
    except Exception as e:
        return f"Screenshot Capture Error: {str(e)}"

    # Messenger API Configuration
    token = getattr(config, "MESSENGER_ACCESS_TOKEN", None)
    if not token:
        return "Error: Messenger token missing in config."
        
    url = f"https://graph.facebook.com/v21.0/me/messages?access_token={token}"
    
    if not os.path.exists(file_path):
        return f"Error: Screenshot file {file_path} was not created."

    try:
        with open(file_path, 'rb') as f:
            files = {'filedata': (os.path.basename(file_path), f, 'image/png')}
            data = {
                'recipient': '{"id": "' + recipient_id + '"}',
                'message': '{"attachment": {"type": "image", "payload": {}}}'
            }
            response = requests.post(url, files=files, data=data)
            if response.status_code == 200:
                return "Successfully captured and sent screenshot to Messenger."
            else:
                return f"Failed to send to Messenger: {response.json()}"
    except Exception as e:
        return f"Messenger API Error: {str(e)}"