@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)
start "" /B ".venv\Scripts\pythonw.exe" "src\main.py"
