import os
import requests
import config
from mcp.mcp_registry import mcp_tool

@mcp_tool(name='utility_tools.bulk_send_injection_context', description='Sends all files in InjectionHeaderContext to Telegram.')
def bulk_send_injection_context(user_id: str = '5662168844'):
    token = getattr(config, 'TELEGRAM_TOKEN', None)
    path = 'D:\\Bane_NLP\\Docs\\InjectionHeaderContext'
    if not os.path.exists(path):
        return f'❌ Path {path} not found.'
    
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    results = []
    url = f'https://api.telegram.org/bot{token}/sendDocument'
    
    for filename in files:
        full_path = os.path.join(path, filename)
        try:
            with open(full_path, 'rb') as f:
                res = requests.post(url, data={'chat_id': user_id}, files={'document': f})
                if res.json().get('ok'):
                    results.append(f'✅ Sent: {filename}')
                else:
                    results.append(f'❌ Failed {filename}: {res.json().get("description")}')
        except Exception as e:
            results.append(f'⚠️ Error {filename}: {str(e)}')
            
    return '\n'.join(results)