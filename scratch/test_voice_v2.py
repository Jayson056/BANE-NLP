import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from services.voice_engine import VoiceEngine
from config import DEFAULT_VOICE

async def test_voice():
    print(f"Testing default voice: {DEFAULT_VOICE}")
    engine = VoiceEngine()
    
    test_text = "This is BANE-NLP Professional V2.0. The voice is optimized for clarity, authority, and a calm, professional delivery."
    
    print("Generating speech...")
    output_path = await engine.generate_speech(test_text)
    
    if output_path and os.path.exists(output_path):
        print(f"SUCCESS! Voice generated at: {output_path}")
        # Note: We keep the file for manual verification if needed, or delete it
        # os.remove(output_path)
    else:
        print("❌ Failed to generate voice.")

if __name__ == "__main__":
    asyncio.run(test_voice())
