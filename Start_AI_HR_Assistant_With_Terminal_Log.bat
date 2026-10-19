@echo off
setlocal
cd /d "%~dp0"

rem Use the project's virtual environment when available.
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    goto :start
)
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
    goto :start
)
if exist "env\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\env\Scripts\python.exe"
    goto :start
)
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :start
)
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    goto :start
)

echo [ERROR] Python was not found. Activate your existing Python environment first.
pause
exit /b 1

:start
"%PYTHON_EXE%" -u "scripts\run_with_terminal_log.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [TERMINAL LOG] Streamlit exited with code %EXIT_CODE%.
    echo [TERMINAL LOG] Review the newest logs\runtime\Terminal_Session_*.log file.
    pause
)
endlocal & exit /b %EXIT_CODE%
