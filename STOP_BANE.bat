@echo off
title Stop Bane Notebook Pipeline
cd /d "%~dp0"

echo ======================================================
echo           Stop Bane Notebook Pipeline (Daemon)
echo ======================================================
echo.
echo Stopping all Bane Engine processes and ngrok...
echo.

:: Kill anything listening on port 5000 (Messenger), 8000 (Portfolio), or 8766 (Bridge)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8766 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

:: Kill Cloudflare Tunnel
taskkill /F /IM cloudflared.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (echo ✅ cloudflared stopped.) else (echo ℹ️ cloudflared was not running.)

:: Kill python processes running run.py
for /f "tokens=2 delims==" %%p in ('wmic process where "name='python.exe' and commandline like '%%run.py%%'" get processid /value ^| find "ProcessId="') do (
    taskkill /F /PID %%p >nul 2>&1
    echo ✅ Bane Engine ^(PID %%p^) stopped.
)

:: Alternative kill just in case wmic fails (kills all pythons so only as last resort, disabled by default)
:: taskkill /F /IM python.exe >nul 2>&1

:: Kill the visible CMD/Terminal Windows left hanging from START_BANE.bat
taskkill /F /FI "WINDOWTITLE eq Bane Engine*" /IM cmd.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Cloudflare Tunnel*" /IM cmd.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Bane Notebook Pipeline Laun*" /IM cmd.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Windows PowerShell" /FI "WINDOWTITLE eq Bane Engine*" >nul 2>&1

echo.
echo 🛑 All requested background processes have been terminated.
timeout /t 5 >nul
exit
