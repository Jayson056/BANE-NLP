from mcp import mcp_tool
import gtts
import os

@mcp_tool(name="media_tools.generate_tts_telegram", description="Generates a TTS audio file and sends it to the user on Telegram")
def generate_tts_telegram(text: str):
  """Generates a TTS audio file and sends it to the user on Telegram."""
  from communication_tools import send_telegram_file
  path = "tts_output.mp3"
  tts = gtts.gTTS(text=text, lang='en')
  tts.save(path)
  return send_telegram_file(path=path)