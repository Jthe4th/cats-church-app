#!/usr/bin/env bash
# Installs a macOS login item that starts the Welcome System server automatically.
# Run once in Terminal after setup: ./scripts/control_panel/INSTALL_AUTOSTART_MAC.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
PANEL="$PROJECT_ROOT/scripts/control_panel/welcome_system_control_panel.py"
PLIST_PATH="$HOME/Library/LaunchAgents/org.welcomesystem.server.plist"

if [ ! -x "$PYTHON" ]; then
  echo "Welcome System setup is incomplete. Create the virtual environment and install requirements first."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.welcomesystem.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$PANEL</string>
    <string>--start-server</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_ROOT</string>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "Automatic startup installed. Welcome System will start when this Mac user logs in."
