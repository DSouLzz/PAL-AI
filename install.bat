@echo off
setlocal
cd /d "%~dp0"
title PAL-AI v0.7 installation

if not exist "config.json" if exist "config.example.json" copy /Y "config.example.json" "config.json" >nul

echo ================================================
echo PAL-AI v0.7 - Windows installation
echo ================================================

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Installing Python 3.12 with winget...
  winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
  echo Restart this installer after Python installation.
  pause
  exit /b 1
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama not found. Installing Ollama with winget...
  winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
  echo Restart Windows or sign out/in, then run install.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
ollama pull gemma3:4b

echo Installation complete. Start PAL-AI with start.bat.
pause
