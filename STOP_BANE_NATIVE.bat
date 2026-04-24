@echo off
title BANE NLP NATIVE STOP
echo ========================================
echo   STOPPING BANE NLP (NATIVE C-MODE)
echo ========================================
echo.

echo [+] Stopping Native C-Backend...
taskkill /F /IM bane_server.exe >nul 2>&1

echo [+] Stopping Native Dashboard...
taskkill /F /IM bane_dashboard.exe >nul 2>&1

echo [+] Stopping Cloudflare Tunnel...
taskkill /F /IM cloudflared.exe >nul 2>&1

echo [+] Stopping Python Brain...
:: We kill python processes running run.py specifically if possible, 
:: but a general taskkill is safer for cleanup
taskkill /F /IM python.exe >nul 2>&1

echo [+] Closing BANE Windows...
taskkill /F /FI "WINDOWTITLE eq BANE_*" /IM cmd.exe >nul 2>&1

echo.
echo ========================================
echo   SYSTEM OFFLINE.
echo ========================================
pause
