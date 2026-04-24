import requests
import os
from mcp.mcp_registry import mcp_tool
import config

@mcp_tool(name='communication_tools.send_telegram_file', description='Sends a local file to a Telegram user.')
def send_telegram_file(file_path: str, user_id: str = None):
    token = getattr(config, 'TELEGRAM_TOKEN', None)
    users = getattr(config, 'ALLOWED_TELEGRAM_USERS', [])
    chat_id = user_id if user_id else (users if isinstance(users, list) and users else None)
    
    if not chat_id:
        return '❌ Error: No chat_id found.'
    
    url = f'https://api.telegram.org/bot{token}/sendDocument'
    
    try:
        if not os.path.exists(file_path):
            return f'❌ Error: File {file_path} not found.'
            
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': chat_id}
            res = requests.post(url, data=data, files=files)
            res_json = res.json()
            
        if res_json.get('ok'):
            return f'✅ File {os.path.basename(file_path)} sent.'
        else:
            return f'❌ Telegram API Error: {res_json.get("description")}'
    except Exception as e:
        return f'❌ Failed: {str(e)}'