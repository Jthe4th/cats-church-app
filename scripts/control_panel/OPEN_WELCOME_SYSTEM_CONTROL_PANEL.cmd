@rem Opens the Welcome System staff control panel on Windows.
@rem Run by double-clicking this file, or from Command Prompt:
@rem scripts\control_panel\OPEN_WELCOME_SYSTEM_CONTROL_PANEL.cmd
@echo off
setlocal
cd /d "%~dp0\..\.."
set "PYTHON=.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Welcome System setup is incomplete.
  echo Run scripts\deploy_windows.cmd first.
  pause
  exit /b 1
)

"%PYTHON%" scripts\control_panel\welcome_system_control_panel.py
if errorlevel 1 pause
