@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================================
echo  Codebase RAG Assistant - first-time setup
echo ============================================================
echo This checks your tools, installs the packages the app needs,
echo and tells you what is still missing. It never downloads an
echo AI model by itself.
echo.

REM ---------- Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto :oldpython
for /f "delims=" %%V in ('%PY% --version') do echo [OK] %%V
goto :venv

:nopython
echo [X] Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" in the installer. Then run setup.bat again.
goto :fail

:oldpython
echo [X] Python 3.10 or newer is required. Install a newer version from https://www.python.org/downloads/
goto :fail

:venv
if exist "backend\.venv\Scripts\python.exe" goto :packages
echo Creating the Python environment in backend\.venv ...
%PY% -m venv backend\.venv
if errorlevel 1 goto :fail

:packages
echo.
echo The backend needs several Python packages. This is a LARGE download
echo (PyTorch for the embedding model: several hundred MB, possibly over 1 GB)
echo and can take a while on a slow connection.
choice /c YN /m "Install or update the backend packages now"
if errorlevel 2 goto :skippackages
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto :fail
echo [OK] Backend packages installed.
goto :config

:skippackages
echo Skipped. Run setup.bat again when you are ready.

:config
if exist "backend\.env" goto :node
copy /y "backend\.env.example" "backend\.env" >nul
echo [OK] Created backend\.env from the example. Review it if you want to change the model.

:node
echo.
where node >nul 2>nul
if errorlevel 1 goto :nonode
where npm >nul 2>nul
if errorlevel 1 goto :nonode
node -e "var v=process.versions.node.split('.').map(Number);process.exit(v[0]>20||(v[0]===20&&v[1]>=19)?0:1)"
if errorlevel 1 goto :oldnode
for /f "delims=" %%V in ('node --version') do echo [OK] Node.js %%V
goto :frontend

:nonode
echo [X] Node.js was not found. Install the LTS version from https://nodejs.org/ and run setup.bat again.
goto :fail

:oldnode
echo [X] Node.js 20.19 or newer is required. Install the current LTS from https://nodejs.org/
goto :fail

:frontend
echo Installing the frontend packages ...
pushd frontend
call npm install
set "NPMERR=%errorlevel%"
popd
if not "%NPMERR%"=="0" goto :fail
echo [OK] Frontend packages installed.

:ollama
echo.
set "MODEL=qwen2.5:3b"
for /f "tokens=2 delims==" %%M in ('findstr /b /c:"OLLAMA_MODEL=" backend\.env 2^>nul') do set "MODEL=%%M"
where ollama >nul 2>nul
if errorlevel 1 goto :noollama
echo [OK] Ollama is installed.
ollama list 2>nul | findstr /i /c:"%MODEL%" >nul
if errorlevel 1 goto :nomodel
echo [OK] The model %MODEL% is downloaded.
goto :done

:noollama
echo [!] Ollama was not found. Questions need it; code search works without it.
echo     1. Install it from https://ollama.com/download
echo     2. Open a new terminal and run:  ollama pull %MODEL%
goto :done

:nomodel
echo [!] The model %MODEL% is not downloaded yet. It is a large download
echo     (qwen2.5:3b is about 1.9 GB, qwen2.5:1.5b about 1 GB). To download it, run:
echo         ollama pull %MODEL%
echo     On a 4 GB RAM computer, consider the smaller model: set OLLAMA_MODEL=qwen2.5:1.5b in backend\.env

:done
echo.
echo ============================================================
echo  Setup finished. Next: double-click start.bat
echo ============================================================
pause
exit /b 0

:fail
echo.
echo Setup stopped because of the problem above. Fix it and run setup.bat again.
pause
exit /b 1
