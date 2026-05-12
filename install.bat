@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not on PATH. Install Python 3.11+ from python.org and re-run.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create venv.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
)

echo.
echo Install complete. Run run.bat to launch the widget.
pause
