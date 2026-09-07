# Welcome System Control Panel

For Welcome System `0.9.13-beta`. See the [Leader Guide](../../WELCOME_LEADER_README.md) for kiosk operation and [Windows Deployment](../../WINDOWS_DEPLOYMENT.md) for installation details.

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

Run the clearly named setup file for the server computer first. It creates `.venv`, installs Waitress and other requirements, applies database migrations, and prepares static files. On Windows, it also checks for Git and installs Git for Windows automatically when Windows Package Manager is available. On a Mac, it prompts for the Apple Command Line Tools when Git is missing. The first Django command also creates `.env` when needed, with an installation secret, debug disabled, and explicit allowed hosts. Check that `DJANGO_ALLOWED_HOSTS` includes the LAN address shown by the panel before opening kiosks. Keep the generated secret; see [Installation Configuration](../../README.md#installation-configuration). Then install optional automatic startup:

### Windows

1. Double-click `SETUP_WELCOME_SYSTEM_WINDOWS.cmd`.
2. Double-click `INSTALL_AUTOSTART_WINDOWS.cmd` if you want the server to start when this Windows account signs in.

### Mac

The Mac setup script does not offer to create an administrator. After setup, run `.venv/bin/python manage.py createsuperuser` from the project folder if this is a new installation.

In Terminal from the project folder, run:

```bash
chmod +x scripts/control_panel/*.sh
./scripts/control_panel/SETUP_WELCOME_SYSTEM_MAC.sh
./scripts/control_panel/INSTALL_AUTOSTART_MAC.sh
```

## Important Notes

- The panel confirms Welcome System through its local health check and can stop a manually started Welcome System server listening on its configured port.
- Do not run more than one Welcome System server on the same port. The panel will report that the server is already running.
- **Install Update** first confirms GitHub can be reached, then creates a backup, stops the server, installs changes from the repository’s `main` branch, updates dependencies, applies migrations, collects static files, and starts the server again. If the app was copied to the computer instead of cloned from GitHub, it connects that folder to the official repository before updating. When installed files differ from GitHub or the installed version is current, it offers to reinstall tracked application files from GitHub instead. The local database, `.env`, uploaded photos, backups, logs, and virtual environment are preserved. Dependencies inside the virtual environment are updated. Repair/reinstall replaces tracked files, so preserve intentional local code changes separately.

- Finish kiosk activity before installing updates. On a failed update, the panel attempts to restart a previously running server; it does not automatically roll back code, dependencies, or migrations.
- Backups contain the database only. Copy `.env` and `media/` separately for recovery. Restores are performed on the admin backup page, require compatible migrations/schema, pause web requests, and sign users out.
- Automatic startup runs when the configured staff account signs in. It does not make the server available before sign-in.
- Configuration changes in `.env` require a restart. The panel’s health checks and displayed links use HTTP; the HTTPS gateway and any associated Control Panel changes need separate deployment validation.

## Logs and Checks

Use **Open Logs Folder** for `logs/welcome-system-server.log` and `logs/welcome-system-server-error.log`. Windows setup also writes `logs/deploy-windows.log`.

Run the Control Panel tests from the project root:

```bash
.venv/bin/python -m unittest discover -s scripts/control_panel/tests
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.
