import subprocess
import os
from mcp_custom.mcp_registry import mcp_custom_tool

@mcp_custom_tool(name="media_tools.text_to_speech_file", description="Fixed TTS via edge-tts module and winget ffmpeg.")
def text_to_speech_file(text: str, output_path: str, voice: str = "en-US-GuyNeural"):
    try:
        # Verified working FFmpeg path
        ffmpeg_path = r'C:\Users\YourPC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe'
        temp_mp3 = output_path.replace('.ogg', '.mp3')
        
        # 1. Generate MP3 via python module (more reliable than direct CLI in some environments)
        cmd_tts = ['python', '-m', 'edge_tts', '--voice', voice, '--text', text, '--write-media', temp_mp3]
        subprocess.run(cmd_tts, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # 2. Convert to OGG using verified FFmpeg
        cmd_conv = [ffmpeg_path, '-y', '-i', temp_mp3, '-c:a', 'libopus', '-b:a', '64k', output_path]
        subprocess.run(cmd_conv, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # Cleanup
        if os.path.exists(temp_mp3): os.remove(temp_mp3)
        
        return f"✅ Success: Audio saved to {output_path}"
    except Exception as e:
        return f"❌ TTS Final Error: {str(e)}"