@echo off
title BANE NLP NATIVE WAKEUP
echo ========================================
echo   WAKING UP BANE NLP (NATIVE C-MODE)
echo ========================================
echo.

:: 1. Cleanup old processes
echo [!] Cleaning up old processes...
taskkill /F /FI "WINDOWTITLE eq BANE_*" /IM cmd.exe >nul 2>&1
taskkill /F /IM bane_server.exe >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1

:: 2. Check for Executables
if not exist "bane_server.exe" (
    echo [!] bane_server.exe missing. Running build script...
    call backend_c\build_bane.bat
)

:: 2. Start Python Brain (Port 5000)
echo [+] Starting Python Brain...
start "BANE_BRAIN_PYTHON" cmd /k "banenv\Scripts\python.exe run.py"

:: 3. Start C-Backend (Port 8080)
echo [+] Starting Native C-Backend...
start "BANE_GATEWAY_C" cmd /k ".\bane_server.exe"

:: 4. Start Cloudflare Tunnel
echo [+] Starting Cloudflare Tunnel...
start "BANE_TUNNEL" cmd /k "cloudflared.exe tunnel --config config.yml run"

:: 5. Start Dashboard
echo [+] Launching Dashboard...
timeout /t 5 >nul
start "BANE_DASHBOARD" cmd /k ".\bane_dashboard.exe"

echo.
echo ========================================
echo   SYSTEM IS ALIVE!
echo   Monitor activity in the Dashboard.
echo ========================================
pause
