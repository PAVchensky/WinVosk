@echo off
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%.venv\Scripts\pythonw.exe" (
    echo Virtual environment is missing. Run: %ROOT%.venv\Scripts\python.exe -m pip install vosk==0.3.45 sounddevice==0.5.6 pystray==0.19.5 Pillow==12.3.0 pyperclip==1.11.0
    pause
    exit /b 1
)
start "" "%ROOT%.venv\Scripts\pythonw.exe" "%ROOT%src\run.py"
endlocal
