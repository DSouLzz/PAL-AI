@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo PAL-AI is not installed yet. Run install.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python pal_ai.py
if errorlevel 1 pause
