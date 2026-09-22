# Welcome System Control Panel

For Welcome System `0.9.15-beta`. See the [Leader Guide](../../WELCOME_LEADER_README.md) for kiosk operation and the [Mac](../../MAC_DEPLOYMENT.md) or [Windows](../../WINDOWS_DEPLOYMENT.md) installation guide for setup details.

This folder contains the simple weekly controls for the church server. Staff should use the Control Panel instead of typing server commands.

For everyday use and first-time setup, double-click **Start Welcome System.command** (Mac) or **Start Welcome System.cmd** (Windows) in the project root. The launcher checks setup, offers preparation if needed, starts the server, waits until it responds, and opens this panel. Accept the desktop shortcut offer to avoid finding the project folder next time.

The legacy setup and panel-only files below remain available. Panel-only launchers do not start the server automatically.

### Desktop shortcuts

After successful startup, the shortcut offer appears once per installation. Declining it is remembered; a creation failure leaves it available on the next launch. To create it later, run from the project folder:

- Mac: `bash "Start Welcome System.command" --shortcut`
- Windows Command Prompt: `"Start Welcome System.cmd" --shortcut`
- Windows PowerShell: `& ".\Start Welcome System.cmd" --shortcut`

Existing desktop items are never overwritten. If you move the project, remove the obsolete shortcut and rerun the command. Shortcut creation failures do not prevent the panel from opening. After setup, the launcher offers optional sign-in startup using the platform-specific scripts below.

## What Each File Does

| File | Use it on | What it does |
| --- | --- | --- |
| `../../Start Welcome System.cmd` | Windows | Recommended setup/start launcher; opens the panel after the server is ready. |
| `../../Start Welcome System.command` | Mac | Recommended setup/start launcher; opens the panel after the server is ready. |
| `launch_welcome_system.py` | Both | Shared launcher implementation; use the top-level files above. |
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
2. Double-click the **Welcome System** desktop shortcut or the platform's **Start Welcome System** file in the project root.
3. Wait for the server to be ready and the Control Panel to open. If you later stop it while the panel is open, use **Start Welcome System** to restart it.
4. Confirm the green status message and use the shown kiosk link on each kiosk device.
5. Press **Create Backup** before the service.
6. At the end of the day, press **Stop Welcome System** only after all kiosks are finished.

The panel also opens the local Admin and Kiosk pages, installs a GitHub update, and opens logs if something fails.

On a Mac with a Python installation that does not include Tkinter, the same controls appear as a numbered Terminal menu instead of a desktop window.

## First-Time Setup

1. Follow [Mac first installation](../../MAC_DEPLOYMENT.md#first-time-installation) or [Windows first installation](../../WINDOWS_DEPLOYMENT.md#first-installation) to download the project and install Python. Git is needed for cloning and updates; the new launcher does not install Git.
2. Open **Start Welcome System.command** (Mac) or **Start Welcome System.cmd** (Windows) in the project root and accept the setup prompt.
3. Setup prepares dependencies, backs up an existing database before migrations, prepares static files, checks configuration, and prompts for an administrator only if no active superuser exists. Stop any existing server before setup; the launcher refuses preparation when port 8000 is in use.
4. Once the server is ready, choose whether to create the desktop shortcut and enable automatic startup at sign-in. The launcher opens the graphical panel, or a numbered Terminal menu when Tkinter is unavailable.
5. Before connecting LAN kiosks, check `DJANGO_ALLOWED_HOSTS` in the generated `.env` and restart after changes. Keep the generated secret. See [Installation Configuration](../../README.md#installation-configuration), then configure accounts and test printing.

Setup needs internet access to install requirements. A ready installation does not reinstall packages on every launch. Setup progress and failures appear in the launcher terminal; setup backups are saved as `backups/before-launcher-setup-*.sqlite3`. The launcher does not download application updates; use **Install Update** in the panel.

### Legacy setup and panel-only entry points

The `SETUP_WELCOME_SYSTEM_...` files remain available for manual troubleshooting. They prepare the app without starting it. The Windows legacy setup can install missing Git and offers an administrator prompt; the Mac legacy setup requires Git and needs a separate `.venv/bin/python manage.py createsuperuser` command for a new installation. Back up existing data and stop the server before running these legacy setup scripts.

The `OPEN_WELCOME_SYSTEM_CONTROL_PANEL...` files open only the controls. With those entry points, press **Start Welcome System** yourself. Prefer the top-level launcher for normal use.

To enable sign-in startup later, double-click `INSTALL_AUTOSTART_WINDOWS.cmd` on Windows, or run `bash scripts/control_panel/INSTALL_AUTOSTART_MAC.sh` from the project root on Mac. The Mac script also loads the server immediately.

## Important Notes

- The panel confirms Welcome System through its local health check and can stop a manually started Welcome System server listening on its configured port.
- Do not run more than one Welcome System server on the same port. The panel will report that the server is already running.
- **Install Update** first confirms GitHub can be reached, then creates a backup, stops the server, installs changes from the repository’s `main` branch, updates dependencies, applies migrations, collects static files, and starts the server again. If the app was copied to the computer instead of cloned from GitHub, it connects that folder to the official repository before updating. When installed files differ from GitHub or the installed version is current, it offers to reinstall tracked application files from GitHub instead. The local database, `.env`, uploaded photos, backups, logs, and virtual environment are preserved. Dependencies inside the virtual environment are updated. Repair/reinstall replaces tracked files, so preserve intentional local code changes separately.

- Finish kiosk activity before installing updates. On a failed update, the panel attempts to restart a previously running server; it does not automatically roll back code, dependencies, or migrations.
- Backups contain the database only. Copy `.env` and `media/` separately for recovery. Restores are performed on the admin backup page, require compatible migrations/schema, pause web requests, and sign users out.
- Closing the Control Panel does not stop the server. Use **Stop Welcome System** after all kiosks are finished.
- Automatic startup runs when the configured staff account signs in. It does not make the server available before sign-in.
- Configuration changes in `.env` require a restart. The panel’s health checks and displayed links use HTTP; the HTTPS gateway and any associated Control Panel changes need separate deployment validation.

## Logs and Checks

Use **Open Logs Folder** for `logs/welcome-system-server.log` and `logs/welcome-system-server-error.log`. The legacy Windows deployment script also writes `logs/deploy-windows.log`; the new launcher's setup output appears in its terminal window.

Run the Control Panel tests from the project root:

```bash
.venv/bin/python -m unittest discover -s scripts/control_panel/tests
```

On Windows, use `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.
