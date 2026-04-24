import requests
import os
from mcp_registry import mcp_tool

@mcp_tool
def messenger_send_screenshot(file_path: str):
    """Sends a screenshot to Messenger using the Graph API."""
    access_token = "EAAWUxUYw6CYBOZC3Rj160oK22mObeN5VqS2e9C7eGshzB0XQ96ZCZALN8uA7jXvZA8Y7uQZA5K2ZBZArY9ZC6ZA9ZC8ZA7ZC"
    recipient_id = "26917714517832064"
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={access_token}"
    
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found."

    try:
        with open(file_path, 'rb') as f:
            files = {'filedata': (os.path.basename(file_path), f, 'image/png')}
            data = {
                'recipient': '{"id": "' + recipient_id + '"}',
                'message': '{"attachment": {"type": "image", "payload": {}}}'
            }
            response = requests.post(url, files=files, data=data)
            return "Successfully sent to Messenger." if response.status_code == 200 else f"Failed: {response.json()}"
    except Exception as e:
        return f"API Error: {str(e)}"