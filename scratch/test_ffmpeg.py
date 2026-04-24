import subprocess
import os

ffmpeg_path = r"D:\Bane_NLP\ffmpeg.exe"
print(f"Testing ffmpeg at {ffmpeg_path}")

try:
    # Run version check
    result = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True)
    if result.returncode == 0:
        print("SUCCESS: ffmpeg is working and all DLLs are present.")
        print(result.stdout.split('\n')[0])
    else:
        print(f"FAILED: ffmpeg returned code {result.returncode}")
        print(result.stderr)
except Exception as e:
    print(f"ERROR: {e}")
