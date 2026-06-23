@echo off
REM Build agent-eye.exe (standalone MCP plugin for Reasonix)
REM Requires: venv with pyinstaller + all deps installed
REM Output:   dist\agent-eye.exe

setlocal
cd /d "%~dp0"

echo === agent-eye build ===

REM Ensure venv exists
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Install deps if needed
echo Installing dependencies...
venv\Scripts\python.exe -m pip install -q uiautomation pyautogui mss pyperclip pillow pyinstaller
echo.

echo Building agent-eye.exe...
venv\Scripts\python.exe -m PyInstaller ^
    --onefile --console ^
    --name agent-eye ^
    --distpath .\dist ^
    --workpath .\build ^
    --clean ^
    --hidden-import comtypes ^
    --hidden-import comtypes.client ^
    --hidden-import comtypes.gen ^
    --hidden-import uiautomation ^
    --hidden-import mss ^
    --hidden-import mss.windows ^
    --hidden-import pyautogui ^
    --hidden-import pyautogui._pyautogui_win ^
    --hidden-import pymsgbox ^
    --hidden-import pyscreeze ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --exclude-module tkinter ^
    --exclude-module unittest ^
    --exclude-module email ^
    src\run.py

if %ERRORLEVEL% equ 0 (
    echo.
    echo === Build OK ===
    for %%I in (dist\agent-eye.exe) do echo    dist\agent-eye.exe  (%%~zI bytes)
    echo.
    echo Test: echo {} ^| dist\agent-eye.exe
) else (
    echo.
    echo === Build FAILED ===
    exit /b %ERRORLEVEL%
)
