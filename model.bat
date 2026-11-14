@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Codebase RAG Assistant - Ollama Model Manager
color 0B

:HOME
cls
echo ============================================================
echo              CODEBASE RAG ASSISTANT
echo                   MODEL MANAGER
echo ============================================================
echo.
echo This tool manages models installed in your local Ollama.
echo Models are downloaded only once and remain available locally.
echo.
echo   [1] Install a model
echo   [2] View installed models
echo   [3] Remove an installed model
echo   [4] Check Ollama version / connection
echo   [5] Exit
echo.
set "CHOICE="
set /p "CHOICE=Enter your choice (1-5): "

if "%CHOICE%"=="1" goto INSTALL
if "%CHOICE%"=="2" goto LIST
if "%CHOICE%"=="3" goto REMOVE
if "%CHOICE%"=="4" goto CHECK
if "%CHOICE%"=="5" goto END

echo.
echo Invalid choice. Please enter a number from 1 to 5.
pause
goto HOME


:CHECK
cls
echo ============================================================
echo                    OLLAMA STATUS
echo ============================================================
echo.
where ollama >nul 2>&1
if errorlevel 1 (
    echo Ollama was not found in PATH.
    echo.
    echo Install Ollama from https://ollama.com/download
    echo Then close and reopen this file.
    echo.
    pause
    goto HOME
)
ollama --version
echo.
echo Checking whether the Ollama service is reachable...
ollama list
if errorlevel 1 (
    echo.
    echo Could not communicate with Ollama.
    echo Start the Ollama application from the Windows Start menu,
    echo wait a few seconds, and try again.
)
echo.
pause
goto HOME


:LIST
cls
echo ============================================================
echo                   INSTALLED MODELS
echo ============================================================
echo.
call :CHECK_OLLAMA
if errorlevel 1 (
    pause
    goto HOME
)
ollama list
echo.
pause
goto HOME


:INSTALL
cls
echo ============================================================
echo                    INSTALL A MODEL
echo ============================================================
echo.
call :CHECK_OLLAMA
if errorlevel 1 (
    pause
    goto HOME
)
echo.
echo Enter an Ollama model name exactly as shown on the Ollama
echo model library, including its tag when applicable.
echo.
echo Examples:
echo   qwen2.5:0.5b
echo   qwen2.5:1.5b
echo   llama3.2:1b
echo.
echo Find more models at: https://ollama.com/library
echo.
set "MODEL_NAME="
set /p "MODEL_NAME=Model name (or type B to go back): "
if not defined MODEL_NAME goto INSTALL
if /i "%MODEL_NAME%"=="B" goto HOME

rem Accept only common Ollama model-name characters.
rem This blocks spaces, quotes, command separators, and shell metacharacters.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$m = $env:MODEL_NAME; if ($m -match '^[A-Za-z0-9][A-Za-z0-9._:/-]*$') { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo.
    echo Invalid model name. Use letters, numbers, dot, underscore,
    echo colon, slash, or hyphen only. Do not include spaces or quotes.
    echo.
    pause
    goto INSTALL
)

echo.
echo Ollama will now download: %MODEL_NAME%
echo Download progress will appear below.
echo Keep this window open until the operation finishes.
echo.
ollama pull "%MODEL_NAME%"
if errorlevel 1 (
    echo.
    echo Model installation failed.
    echo Check the model name, internet connection, disk space,
    echo and whether the Ollama application is running.
) else (
    echo.
    echo SUCCESS: %MODEL_NAME% is installed.
)
echo.
choice /c YN /n /m "Would you like to install another model? [Y/N]: "
if errorlevel 2 goto HOME
goto INSTALL


:REMOVE
cls
echo ============================================================
echo                   REMOVE A MODEL
echo ============================================================
echo.
call :CHECK_OLLAMA
if errorlevel 1 (
    pause
    goto HOME
)
echo.
echo Installed models:
ollama list
echo.
echo WARNING: Removing a model deletes its local downloaded files.
echo You can download it again later using this manager.
echo.
set "MODEL_NAME="
set /p "MODEL_NAME=Enter the exact model name to remove (or B to go back): "
if not defined MODEL_NAME goto REMOVE
if /i "%MODEL_NAME%"=="B" goto HOME

powershell -NoProfile -ExecutionPolicy Bypass -Command "$m = $env:MODEL_NAME; if ($m -match '^[A-Za-z0-9][A-Za-z0-9._:/-]*$') { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo.
    echo Invalid model name. Use letters, numbers, dot, underscore,
    echo colon, slash, or hyphen only.
    echo.
    pause
    goto REMOVE
)

echo.
choice /c YN /n /m "Confirm removal of %MODEL_NAME%? [Y/N]: "
if errorlevel 2 goto HOME
ollama rm "%MODEL_NAME%"
if errorlevel 1 (
    echo.
    echo Could not remove the model. Check the exact model name.
) else (
    echo.
    echo Model removal completed.
)
echo.
pause
goto HOME


:CHECK_OLLAMA
where ollama >nul 2>&1
if errorlevel 1 (
    echo Ollama was not found in PATH.
    echo Install it from https://ollama.com/download
    echo and reopen this file.
    exit /b 1
)
ollama list >nul 2>&1
if errorlevel 1 (
    echo Ollama is installed, but its local service is not reachable.
    echo Start the Ollama application from the Windows Start menu,
    echo wait a few seconds, and try again.
    exit /b 1
)
exit /b 0


:END
echo.
echo Model Manager closed.
endlocal
exit /b 0
