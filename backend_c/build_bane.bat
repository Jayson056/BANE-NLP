@echo off
title BANE NLP Native Build Tool
echo ========================================
echo   BANE NLP NATIVE COMPILER (v2.0-C)
echo ========================================
echo.

:: Check for GCC or Clang
set COMPILER=
where gcc >nul 2>nul && set "COMPILER=gcc"
if not defined COMPILER (
    where clang >nul 2>nul && set "COMPILER=clang"
)
if not defined COMPILER (
    if exist "C:\Users\YourPC\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260407-ucrt-x86_64\bin\clang.exe" (
        set "COMPILER=C:\Users\YourPC\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260407-ucrt-x86_64\bin\clang.exe"
    )
)
if not defined COMPILER (
    if exist "C:\Program Files\LLVM\bin\clang.exe" (
        set "COMPILER=C:\Program Files\LLVM\bin\clang.exe"
    )
)

if not defined COMPILER (
    echo [!] ERROR: C Compiler not found.
    echo Please restart your terminal or install LLVM.
    echo.
    pause
    exit /b
)

echo [+] Using Compiler: "%COMPILER%"

echo [+] Compiling BANE C-Server...
"%COMPILER%" bane_server.c -o ..\bane_server.exe -lws2_32
if %errorlevel% equ 0 (
    echo [OK] bane_server.exe created.
) else (
    echo [FAIL] Server compilation failed.
)

echo [+] Compiling BANE C-Dashboard...
"%COMPILER%" bane_dashboard.c -o ..\bane_dashboard.exe -lws2_32
if %errorlevel% equ 0 (
    echo [OK] bane_dashboard.exe created.
) else (
    echo [FAIL] Dashboard compilation failed.
)

echo.
echo ========================================
echo BUILD COMPLETE!
echo.
echo 1. Run bane_server.exe to start the High-Speed Backend.
echo 2. Run bane_dashboard.exe to see the Live Pipeline.
echo ========================================
pause
