import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
import os
import tempfile
import asyncio
import edge_tts
import subprocess

@mcp_custom_tool(name="media_tools.text_to_speech_file", description="Converts text string to an audio file using edge-tts. Args: {'text': 'the exact text to say', 'output_path': 'path to output file (.ogg)', 'voice': '(optional) en-US-GuyNeural (male) or en-US-JennyNeural (female)'}")
async def text_to_speech_file(text: str, output_path: str, voice: str = "en-US-GuyNeural") -> str:
    try:
        text = text.strip()
        if not text:
            return "Error: Input text is empty."
            
        # Auto-correct common backslash escaping issues like \t inside temp_audio becoming a tab
        output_path = output_path.replace('\t', 't')
        
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            
        # We save directly to a temp mp3, then explicitly convert to telegram-playable Ogg Opus using ffmpeg
        temp_mp3 = tempfile.mktemp(suffix=".mp3")
        
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(temp_mp3)
        
        if output_path.lower().endswith('.ogg'):
            # Convert to strictly formatted Libopus OGG for telegram asynchronously
            # Optimized for speed and small file size (faster upload)
            proc = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-i', temp_mp3,
                '-c:a', 'libopus',
                '-b:a', '24k',          # Lower bitrate
                '-ac', '1',             # Mono
                '-application', 'voip',   # Optimized for speech
                '-threads', '0',
                output_path,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            
            if proc.returncode != 0:
                return f"Error: ffmpeg conversion failed with exit code {proc.returncode}"
                
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
        else:
            # If not ogg, just rename mp3 or convert normally
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_mp3, output_path)

        return f"Audio successfully generated at {output_path} using voice {voice}"
    except Exception as e:
        import traceback
        return f"Error: {e}\n{traceback.format_exc()}"
