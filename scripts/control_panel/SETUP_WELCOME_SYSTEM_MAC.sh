#!/usr/bin/env bash
# Performs the one-time Mac setup: creates the virtual environment and prepares Welcome System.
# Run in Terminal before using the control panel: ./scripts/control_panel/SETUP_WELCOME_SYSTEM_MAC.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Welcome System first-time setup"
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check

echo
echo "Setup complete. Open the Control Panel with:"
echo "  ./scripts/control_panel/OPEN_WELCOME_SYSTEM_CONTROL_PANEL.sh"
