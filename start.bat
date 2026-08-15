@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo PAL-AI is not installed yet. Run install.bat first.
  pause
  exit /b 1
)
start "" /B ".venv\Scripts\pythonw.exe" launcher.py
exit /b 0
