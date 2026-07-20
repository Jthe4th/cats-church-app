@rem Installs a Windows sign-in task that starts the Welcome System server automatically.
@rem Run once after setup by double-clicking this file, or from Command Prompt:
@rem scripts\control_panel\INSTALL_AUTOSTART_WINDOWS.cmd
@echo off
setlocal
cd /d "%~dp0\..\.."
set "PYTHON=%CD%\.venv\Scripts\python.exe"
set "PANEL=%CD%\scripts\control_panel\welcome_system_control_panel.py"

if not exist "%PYTHON%" (
  echo Welcome System setup is incomplete.
  echo Run scripts\deploy_windows.cmd first.
  pause
  exit /b 1
)

schtasks /create /tn "Welcome System Server" /sc onlogon /rl limited /f /tr "\"%PYTHON%\" \"%PANEL%\" --start-server"
echo.
echo Automatic startup has been installed for this Windows account.
pause
