@echo off
setlocal
cd /d "%~dp0\.."
echo.
echo Starting Welcome System deployment...
echo Project folder: %CD%
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_windows.ps1" -WaitAtEnd
echo.
echo If the window is still open because of an error, read the message above.
pause
