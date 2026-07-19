@echo off
setlocal
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1" -WaitAtEnd
echo.
echo If the window is still open because of an error, read the message above.
pause
