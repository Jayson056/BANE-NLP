"""
BANE V4 — Media Tools
=======================
Image manipulation, audio info, and media file handling.
"""

import os
import subprocess
import sys
import base64
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event


@mcp_custom_tool(
    name="media_tools.get_image_info",
    description="Get image metadata (dimensions, size, format). Args: {'path': 'image.png'}"
)
def get_image_info(path: str = "") -> str:
    """Get image file information."""
    if not path:
        return "❌ Error: 'path' is required."
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    
    info = [
        f"File: {os.path.basename(path)}",
        f"Path: {os.path.abspath(path)}",
        f"Format: {ext}",
        f"Size: {size / 1024:.1f} KB",
    ]
    
    # Try to get dimensions using PowerShell
    try:
        ps_cmd = f"""
        Add-Type -AssemblyName System.Drawing
        $img = [System.Drawing.Image]::FromFile('{os.path.abspath(path)}')
        Write-Output "$($img.Width)x$($img.Height)"
        $img.Dispose()
        """
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0 and result.stdout.strip():
            info.append(f"Dimensions: {result.stdout.strip()}")
    except:
        pass
    
    return "\n".join(info)


@mcp_custom_tool(
    name="media_tools.convert_image",
    description="Convert an image to a different format. Args: {'input': 'photo.bmp', 'output': 'photo.png'}"
)
def convert_image(input: str = "", output: str = "") -> str:
    """Convert image between formats using PowerShell."""
    if not input or not output:
        return "❌ Error: 'input' and 'output' paths are required."
    if not os.path.exists(input):
        return f"❌ Input file not found: {input}"
    
    out_ext = os.path.splitext(output)[1].lower()
    format_map = {
        ".png": "Png", ".jpg": "Jpeg", ".jpeg": "Jpeg",
        ".bmp": "Bmp", ".gif": "Gif", ".tiff": "Tiff"
    }
    
    fmt = format_map.get(out_ext)
    if not fmt:
        return f"❌ Unsupported output format: {out_ext}. Supported: {list(format_map.keys())}"
    
    try:
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        ps_cmd = f"""
        Add-Type -AssemblyName System.Drawing
        $img = [System.Drawing.Image]::FromFile('{os.path.abspath(input)}')
        $img.Save('{os.path.abspath(output)}', [System.Drawing.Imaging.ImageFormat]::{fmt})
        $img.Dispose()
        """
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if os.path.exists(output):
            return f"✅ Converted {input} → {output}"
        return f"❌ Conversion failed: {result.stderr.strip()}"
    except Exception as e:
        return f"❌ Conversion failed: {e}"


@mcp_custom_tool(
    name="media_tools.image_to_base64",
    description="Convert an image file to base64 string. Args: {'path': 'image.png'}"
)
def image_to_base64(path: str = "") -> str:
    """Read image and return base64 encoded string."""
    if not path:
        return "❌ Error: 'path' is required."
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", 
                "gif": "image/gif", "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        
        # Truncate if too large
        if len(data) > 8000:
            return f"Base64 ({len(data)} chars, {mime}): {data[:500]}...[TRUNCATED]"
        
        return f"data:{mime};base64,{data}"
    except Exception as e:
        return f"❌ Encoding failed: {e}"


@mcp_custom_tool(
    name="media_tools.list_media_files",
    description="List all media files (images, videos, audio) in a directory. Args: {'path': '.'}"
)
def list_media_files(path: str = ".") -> str:
    """List media files in a directory."""
    import glob
    
    media_exts = {
        "Images": ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp", "*.svg"],
        "Videos": ["*.mp4", "*.avi", "*.mkv", "*.mov", "*.webm"],
        "Audio": ["*.mp3", "*.wav", "*.ogg", "*.flac", "*.m4a", "*.aac"],
    }
    
    results = []
    total = 0
    
    for category, patterns in media_exts.items():
        files = []
        for pattern in patterns:
            files.extend(glob.glob(os.path.join(path, "**", pattern), recursive=True))
        
        if files:
            results.append(f"\n📁 {category} ({len(files)}):")
            for f in files[:15]:
                size = os.path.getsize(f) / 1024
                results.append(f"  📄 {os.path.relpath(f, path)} ({size:.1f} KB)")
            if len(files) > 15:
                results.append(f"  ... and {len(files) - 15} more")
            total += len(files)
    
    if not results:
        return f"No media files found in {path}."
    
    return f"Found {total} media files:" + "\n".join(results)
