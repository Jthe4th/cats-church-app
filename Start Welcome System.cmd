@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\control_panel\launch_welcome_system.py %*
  goto done
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 scripts\control_panel\launch_welcome_system.py %*
  goto done
)
python --version >nul 2>&1
if not errorlevel 1 (
  python scripts\control_panel\launch_welcome_system.py %*
  goto done
)
echo Install Python 3.10 or newer from https://www.python.org/downloads/, then open this file again.
pause
exit /b 1
:done
if errorlevel 1 (
  pause
  exit /b 1
)
