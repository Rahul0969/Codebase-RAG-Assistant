@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo  Codebase RAG Assistant
echo ============================================================
if not exist "backend\.venv\Scripts\python.exe" goto :needsetup
if not exist "frontend\node_modules" goto :needsetup

where ollama >nul 2>nul
if errorlevel 1 echo [!] Ollama was not found: questions will not work until you install it. Search still works.

echo Opening two windows: one for the backend, one for the web page.
echo Both stay open so you can see errors. Close a window or press Ctrl+C in it to stop it.
start "Codebase RAG - Backend" cmd /k call "%~dp0start-backend.bat"
start "Codebase RAG - Web page" cmd /k call "%~dp0start-frontend.bat"

echo Waiting a few seconds, then opening your browser at http://127.0.0.1:5173 ...
timeout /t 6 /nobreak >nul
start "" "http://127.0.0.1:5173"
echo.
echo You can close this window. To stop the app, close the two other windows.
pause
exit /b 0

:needsetup
echo Setup has not been completed. Run setup.bat first.
pause
exit /b 1
