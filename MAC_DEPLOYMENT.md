# Mac Setup and Usage

Applies to Welcome System `0.9.13-beta`. For Windows, use [Windows Deployment](WINDOWS_DEPLOYMENT.md). The [Leader Guide](WELCOME_LEADER_README.md) covers check-in on either platform.

## Before Setup

Use one Mac as the server; kiosks connect to it through their browsers. Keep the server awake and connected to the church network while check-in is in use.

The setup script requires `python3` with pip and venv, and Git. Check them in Terminal:

```bash
python3 --version
git --version
```

If Git is missing, run `xcode-select --install`, finish the Command Line Tools installation, and retry. If Python is missing, install Python before continuing. The optional graphical Control Panel uses Tkinter; when it is unavailable, the panel provides a numbered Terminal menu.

## First-Time Installation

Open Terminal and run:

```bash
mkdir -p "$HOME/Applications"
cd "$HOME/Applications"
git clone https://github.com/Jthe4th/cats-church-app.git WelcomeSystem
cd WelcomeSystem
chmod +x scripts/control_panel/*.sh scripts/control_panel/*.command
./scripts/control_panel/SETUP_WELCOME_SYSTEM_MAC.sh
.venv/bin/python manage.py createsuperuser
```

Stop and resolve any error before running the next command. The setup script creates `.venv`, installs requirements, applies database migrations, collects static files, and checks the application. It does not start the server or create an administrator automatically; the final command above creates that account.

The first Django command creates a private `.env` file when needed. It contains an installation-specific secret, debug disabled, and allowed local hostnames/addresses. Keep the generated secret. Do not overwrite it with the placeholder in `.env.example`.

## Configure Network Access

Edit `.env` in the project folder. Hidden files can be shown in Finder with Command–Shift–Period. Set `DJANGO_ALLOWED_HOSTS` to the server names and IP addresses used by the kiosks, without port numbers. For example:

```text
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1],church-mac.local,192.168.1.10
DJANGO_HTTPS=False
```

Replace the example hostname and IP with your Mac's actual values. Use the network address shown in macOS Network settings, or the hostname shown by the Control Panel. If a hostname does not resolve on a kiosk, use the LAN IP and include it in the allowed hosts. Restart Welcome System after changing `.env`.

If the macOS firewall blocks incoming connections, allow the server's Python application for the church network. Do not forward port 8000 from the internet-facing router. Leave HTTPS disabled until a separate HTTPS gateway has been configured and tested.

## Start and Use the System

1. In Finder, open the project folder and double-click `scripts/control_panel/OPEN_WELCOME_SYSTEM_CONTROL_PANEL.command`. Alternatively, run `./scripts/control_panel/OPEN_WELCOME_SYSTEM_CONTROL_PANEL.sh` from the project folder in Terminal.
2. Click **Start Welcome System**, or select that action in the Terminal menu. The server uses Waitress.
3. Open **Admin** at `http://127.0.0.1:8000/admin/` and sign in with the administrator account.
4. Configure Greeter/Staff accounts and permissions using [Accounts and Permissions](README.md#accounts-and-permissions), then confirm the current service is open.
5. On each kiosk, open `http://SERVER-IP:8000/kiosk/?kiosk=kiosk1`, changing the ID to `kiosk2`, `kiosk3`, and so on. Replace `SERVER-IP` with the Mac's LAN address. Do not use `127.0.0.1` on another device.
6. Sign in with a Greeter account, check the kiosk ID and service, and print a test label if printing is enabled.
7. Create a backup before the service. Follow the [Leader Guide](WELCOME_LEADER_README.md) for family check-in, new visitors, and troubleshooting.
8. After check-in finishes, close the service as appropriate, close the kiosk browsers, and select **Stop Welcome System** before shutting down the Mac.

### Optional Automatic Startup

After setup and account configuration, run from the project folder:

```bash
./scripts/control_panel/INSTALL_AUTOSTART_MAC.sh
```

This installs a LaunchAgent that starts the server when this Mac user signs in. It also loads the agent immediately, so the server may start as soon as installation finishes. The Mac must still be awake and signed in; this is not startup before login.

## Printer Setup

For Server Printer queue mode, install the printer in macOS Printers & Scanners and verify that it prints. In Terminal, `lpstat -p` lists print queue names. Use the exact queue name in the kiosk's printer profile or fallback `server_printer_map`, for example `{"kiosk1": "queue:Brother_QL_820NWB"}`.

The Mac queue backend submits PDF labels through `lp`; Windows queue mode uses its installed printer driver. PrintNode and direct network printing are also available. See [Printing](README.md#printing) for profiles, label settings, and mappings. A “ready” status confirms configuration; use **Test Printer** to verify physical output.

## Updates

Finish kiosk activity, then choose **Check for updates** and **Install Update** in the Control Panel. It creates a database backup, stops the server, installs changes and requirements, applies migrations, collects static files, and restarts. No separate stop/start is needed for this normal path.

Repair/reinstall replaces tracked application files. Preserve intentional code edits separately. On update failure, the panel tries to restart a previously running server, but does not roll back code, dependencies, or migrations automatically.

### Manual Update or Recovery

If the panel is unavailable, stop the server with `Ctrl+C` in its server terminal. If it was started in the background, identify its process using `lsof -nP -iTCP:8000 -sTCP:LISTEN`, confirm it is Welcome System, and stop that process before proceeding.

From the project folder, run each command only after the preceding command succeeds:

```bash
.venv/bin/python manage.py shell -c "from core.backups import create_database_backup; print(create_database_backup(label='before-update').path)"
git pull --ff-only origin main
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check
.venv/bin/python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
```

Leave the final Terminal window open while the server is in use, and press `Ctrl+C` to stop it. Verify the admin page, kiosk check-in, and a test label after updating.

## Backups and Troubleshooting

- **Create Backup** stores the database in `backups/`. Preserve `.env` and `media/` separately; database backups do not contain configuration or photos.
- Restore through the admin backup page using a compatible backup. Restoration pauses check-in and signs everyone out. See [Recovery and Connection Behavior](README.md#recovery-and-connection-behavior).
- Use **Open Logs Folder** to inspect `logs/welcome-system-server.log` and `logs/welcome-system-server-error.log`. A manually started foreground server writes to its Terminal window.
- If Finder reports a permission problem opening the launcher, rerun the `chmod` command from setup or use the Terminal launcher.
- For “Bad Request (400)”, check the requested hostname/IP against `.env`, then restart. For a connection failure, check server status, network connectivity, firewall access, and whether the Mac is asleep.
- Check-in requires a live connection. If submission cannot be confirmed, search again for attendance and inspect the printer before retrying a print.
