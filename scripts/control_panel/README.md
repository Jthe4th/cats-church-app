# Welcome System Control Panel

This folder contains the simple weekly controls for the church server. Staff should use the Control Panel instead of typing server commands.

Start with the one-time `SETUP_WELCOME_SYSTEM_...` file for the server's operating system. After setup, open the matching `OPEN_WELCOME_SYSTEM_CONTROL_PANEL...` file each week. The files themselves have a short description and run instruction at the top.

## What Each File Does

| File | Use it on | What it does |
| --- | --- | --- |
| `SETUP_WELCOME_SYSTEM_WINDOWS.cmd` | Windows | One-time application setup. Does not start the server. |
| `SETUP_WELCOME_SYSTEM_MAC.sh` | Mac | One-time application setup. Does not start the server. |
| `OPEN_WELCOME_SYSTEM_CONTROL_PANEL.cmd` | Windows | Double-click to open the staff control panel. |
| `OPEN_WELCOME_SYSTEM_CONTROL_PANEL.sh` | Mac | Run from Terminal to open the staff control panel. |
| `OPEN_WELCOME_SYSTEM_CONTROL_PANEL.command` | Mac | Double-click in Finder to open the staff control panel. |
| `INSTALL_AUTOSTART_WINDOWS.cmd` | Windows | Optional one-time setup: starts Welcome System when the staff user signs in. |
| `INSTALL_AUTOSTART_MAC.sh` | Mac | Optional one-time setup: starts Welcome System when the staff user signs in. |
| `welcome_system_control_panel.py` | Both | The application behind the buttons. Do not open this file directly. |

## Weekly Use

1. Turn on the church server computer and sign in.
2. Open the Control Panel.
3. Press **Start Welcome System** if it is not already running.
4. Confirm the green status message and use the shown kiosk link on each kiosk device.
5. Press **Create Backup** before the service.
6. At the end of the day, press **Stop Welcome System** only after all kiosks are finished.

The panel also opens the local Admin and Kiosk pages, installs a GitHub update, and opens logs if something fails.

On a Mac with a Python installation that does not include Tkinter, the same controls appear as a numbered Terminal menu instead of a desktop window.

## First-Time Setup

Run the clearly named setup file for the server computer first. It creates `.venv`, installs Waitress and other requirements, applies database migrations, and prepares static files. Then install optional automatic startup:

### Windows

1. Double-click `SETUP_WELCOME_SYSTEM_WINDOWS.cmd`.
2. Double-click `INSTALL_AUTOSTART_WINDOWS.cmd` if you want the server to start when this Windows account signs in.

### Mac

In Terminal from the project folder, run:

```bash
chmod +x scripts/control_panel/*.sh
./scripts/control_panel/SETUP_WELCOME_SYSTEM_MAC.sh
./scripts/control_panel/INSTALL_AUTOSTART_MAC.sh
```

## Important Notes

- The panel confirms Welcome System through its local health check and can stop a manually started Welcome System server listening on its configured port.
- Do not run more than one Welcome System server on the same port. The panel will report that the server is already running.
- **Install Update** creates a backup, stops the server, pulls approved changes from `main`, updates dependencies, applies migrations, collects static files, and starts the server again.
