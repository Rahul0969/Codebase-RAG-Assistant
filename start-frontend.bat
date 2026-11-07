@echo off
setlocal EnableExtensions
cd /d "%~dp0frontend"
title Codebase RAG - Web page
if not exist "node_modules" (
  echo The web page packages are missing. Run setup.bat first.
  pause
  exit /b 1
)
echo Starting the web page at http://127.0.0.1:5173 . Press Ctrl+C to stop it.
echo.
call npm run dev
echo.
echo The web page server has stopped. Read any error message above.
pause
