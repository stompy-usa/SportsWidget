@echo off
setlocal
cd /d "%~dp0"

set "TARGET=%~dp0run.bat"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\SportsWidget.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
    "$s.TargetPath='%TARGET%';" ^
    "$s.WorkingDirectory='%~dp0';" ^
    "$s.WindowStyle=7;" ^
    "$s.Save()"

if errorlevel 1 (
    echo Failed to create startup shortcut.
    pause
    exit /b 1
)
echo Startup shortcut created at:
echo   %LINK%
echo Widget will launch automatically at login. Delete the shortcut to disable.
pause
