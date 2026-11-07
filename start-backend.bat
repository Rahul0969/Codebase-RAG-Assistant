@echo off
setlocal EnableExtensions
cd /d "%~dp0backend"
title Codebase RAG - Backend
if not exist ".venv\Scripts\python.exe" (
  echo The Python environment is missing. Run setup.bat first.
  pause
  exit /b 1
)
echo Starting the backend. It listens on this computer only. Press Ctrl+C to stop it.
echo.
".venv\Scripts\python.exe" run_api.py
echo.
echo The backend has stopped. Read any error message above.
pause
