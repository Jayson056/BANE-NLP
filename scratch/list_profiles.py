import json
import os

def list_chrome_profiles():
    local_state_path = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Local State')
    
    if not os.path.exists(local_state_path):
        print("Error: Chrome Local State file not found.")
        return

    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        info_cache = data.get('profile', {}).get('info_cache', {})
        
        print("--- CHROME PROFILES DETECTED ---")
        for dir_name, info in info_cache.items():
            name = info.get('name', 'Unknown')
            user_name = info.get('user_name', '')
            print(f"Directory: {dir_name} | Profile Name: {name} ({user_name})")
            
    except Exception as e:
        print(f"Error reading profiles: {str(e)}")

if __name__ == "__main__":
    list_chrome_profiles()
