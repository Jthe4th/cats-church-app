@echo off
setlocal
cd /d "%~dp0\.."
echo.
echo Starting Welcome System printer diagnostics...
echo Project folder: %CD%
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0printer_diagnostics_windows.ps1"
echo.
pause
