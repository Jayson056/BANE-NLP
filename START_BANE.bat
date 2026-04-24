@echo off
title Bane Notebook Pipeline Launcher
cd /d "%~dp0"

echo ======================================================
echo           Bane Notebook Pipeline Launcher
echo ======================================================
echo.

:: Check if virtual environment exists
if not exist "banenv\Scripts\activate" (
    echo [ERROR] Virtual environment 'banenv' not found!
    echo Please make sure you are in the correct folder.
    pause
    exit
)

:: Clean up old hanging windows from previous sessions to prevent clutter
taskkill /F /FI "WINDOWTITLE eq Bane Engine*" /IM cmd.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Cloudflare Tunnel*" /IM cmd.exe >nul 2>&1

echo [1/2] Starting Bane Engine (run.py)...
start "Bane Engine" cmd /c "banenv\Scripts\activate && python run.py"

timeout /t 3 >nul

echo [2/2] Starting Cloudflare Tunnel (jayson056.space)...
start "Cloudflare Tunnel" cmd /c "cloudflared.exe tunnel --config config.yml run"

echo.
echo ✅ Both services are starting in separate windows.
echo 🚀 KEEP BOTH WINDOWS OPEN for Bane to work.
echo.
echo 📌 Your Messenger webhook is now: https://jayson056.space/webhooks/messenger
echo    (Verify this is set in Meta for Developers dashboard)
echo.
pause
