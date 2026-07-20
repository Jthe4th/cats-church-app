#!/usr/bin/env bash
# Opens the Welcome System staff control panel from a Mac or Linux Terminal.
# Run after setup: ./scripts/control_panel/OPEN_WELCOME_SYSTEM_CONTROL_PANEL.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Welcome System setup is incomplete. Create the virtual environment and install requirements first."
  exit 1
fi

cd "$PROJECT_ROOT"
exec "$PYTHON" scripts/control_panel/welcome_system_control_panel.py
