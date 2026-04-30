import urllib.request
import json
import os

print("Fetching latest TGPT release info...")
url = "https://api.github.com/repos/aandrew-me/tgpt/releases/latest"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    download_url = None
    for asset in data.get('assets', []):
        name = asset.get('name', '').lower()
        print("Asset found:", name)
        if name == 'tgpt-amd64.exe':
            download_url = asset.get('browser_download_url')
            break
            
    if download_url:
        print(f"Downloading from: {download_url}")
        target_path = os.path.expanduser("~\\AppData\\Local\\tgpt\\tgpt.exe")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Backup the old one just in case
        if os.path.exists(target_path):
            try:
                os.remove(target_path + ".bak")
            except: pass
            try:
                os.rename(target_path, target_path + ".bak")
            except Exception as e:
                print(f"Could not rename old tgpt: {e}")
                
        urllib.request.urlretrieve(download_url, target_path)
        print("Successfully downloaded and installed TGPT.")
    else:
        print("Could not find Windows AMD64 asset in the latest release.")
except Exception as e:
    print(f"Error: {e}")
