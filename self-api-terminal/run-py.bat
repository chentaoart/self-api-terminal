@echo off
rem Fallback launcher: run the app from source, for when the packaged exe is blocked.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] .venv not found next to this script.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" app.py
