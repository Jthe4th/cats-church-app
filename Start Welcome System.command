#!/bin/bash
# Double-click this file in Finder for setup, startup, and the Control Panel.
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "Install Python 3.10 or newer from https://www.python.org/downloads/, then open this file again."
  read -r -p "Press Enter to close."
  exit 1
fi
"$PYTHON" scripts/control_panel/launch_welcome_system.py "$@"
RESULT=$?
if [ "$RESULT" -ne 0 ]; then
  read -r -p "Press Enter to close."
fi
exit "$RESULT"
