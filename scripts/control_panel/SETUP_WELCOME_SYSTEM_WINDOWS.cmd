@rem Performs the one-time Windows setup: installs dependencies and prepares Welcome System.
@rem Run before using the control panel by double-clicking this file, or from Command Prompt:
@rem scripts\control_panel\SETUP_WELCOME_SYSTEM_WINDOWS.cmd
@echo off
setlocal
cd /d "%~dp0\..\.."

echo Welcome System first-time setup
echo This installs requirements, applies database updates, and prepares static files.
echo The server will be started later from the Control Panel.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\deploy_windows.ps1" -NoStart -WaitAtEnd
