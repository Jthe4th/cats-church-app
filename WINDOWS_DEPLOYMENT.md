# Windows Deployment

Applies to Welcome System `0.9.14-beta`. For Mac, use [Mac Setup and Usage](MAC_DEPLOYMENT.md). For routine check-in on either platform, use the [Leader Guide](WELCOME_LEADER_README.md).

These instructions deploy Welcome System on the church Windows PC and make it available to other devices on the local network.

Repository: [Jthe4th/cats-church-app](https://github.com/Jthe4th/cats-church-app)

## Recommended Setup and Launch

After downloading the project and installing Python 3.10 or newer, double-click **Start Welcome System.cmd** in the top-level project folder. Use this same file every time.

- If setup is incomplete, the launcher offers to install dependencies, back up an existing database, apply migrations, prepare static files, and create an administrator when needed. Initial setup needs internet access.
- If ready, it starts the server and waits for a successful health check before opening the Control Panel. An already-running server is left running.
- Accept the desktop shortcut offer to launch from **Welcome System** next time. The shortcut points to this folder; recreate it if you move the project.
- Continue with network, user permissions, and printer configuration below. Git is needed for Control Panel updates.
- After completing setup, the launcher also offers optional automatic startup at sign-in. You can enable it later using the instructions below.

Follow the installation steps below once; use the launcher or desktop shortcut for subsequent starts.

## Requirements

Install the following on the Windows PC:

1. Python with pip and venv (the deployment baseline is Python 3.12) from [Python for Windows](https://www.python.org/downloads/windows/).
   Select **Add Python to PATH** during installation.
2. [Git for Windows](https://git-scm.com/download/win).
3. The full Windows driver for each label printer.

The PC and label printers should be connected to the same local network.

## First Installation

Open PowerShell and run:

```powershell
cd C:\
git clone https://github.com/Jthe4th/cats-church-app.git WelcomeSystem
cd C:\WelcomeSystem
& ".\Start Welcome System.cmd"
```

Accept **Run setup now?** when prompted. The launcher creates the virtual environment, installs requirements, initializes configuration when needed, backs up an existing database before migrations, prepares static files, and checks the application. If no active superuser exists, it runs the administrator-creation prompts.

It then starts the server, waits until it responds, offers a desktop shortcut and optional sign-in startup, and opens the Control Panel. If a step fails, resolve the reported error and reopen the same launcher. If you downloaded a ZIP instead of cloning, extract it into a permanent folder first, then double-click **Start Welcome System.cmd**.

## Everyday Startup

Double-click the **Welcome System** desktop shortcut, or **Start Welcome System.cmd** in the project folder. An already-running server is left running; otherwise the launcher starts it before opening the controls. Keep the server PC powered on while kiosks are in use. Use **Stop Welcome System** in the panel after all kiosks are finished; closing the panel does not stop the server.

### Optional Automatic Startup

Accept the sign-in-startup offer after launcher setup, or double-click `scripts\control_panel\INSTALL_AUTOSTART_WINDOWS.cmd` later. This starts the server when the configured Windows account signs in, not before sign-in. You can still use the desktop shortcut to open the controls.

## Configure the Server Address and Accounts

Before opening LAN kiosks, edit the generated `.env` file in `C:\WelcomeSystem`. Keep its generated `DJANGO_SECRET_KEY`; do not replace it with the placeholder in `.env.example`.

Set `DJANGO_ALLOWED_HOSTS` to the names and addresses people will use, without port numbers. For example:

```text
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1],CHURCH-PC-NAME,192.168.1.10
DJANGO_HTTPS=False
```

Replace the example name and IP with the actual server values. Restart after changing `.env`. If the LAN IP changes, update the allowed hosts and kiosk bookmarks. Leave `DJANGO_HTTPS=False` for the existing HTTP setup; enable it only after HTTPS is configured.

Use the administrator account to set up users. Migrations create Greeter, Admin, and Pastor groups without assigning model permissions. Greeters need Greeter or Admin membership. Staff/admin users need staff status and Admin or Pastor membership, plus the appropriate Django model permissions. Service actions require `core.change_service`. See [Accounts and Permissions](README.md#accounts-and-permissions).

## Application URLs

On the server PC:

- Admin: `http://localhost:8000/admin/`
- Kiosk: `http://localhost:8000/kiosk/?kiosk=kiosk1`

From another device on the church network, replace `CHURCH-PC-NAME` with the Windows computer name:

- Admin: `http://CHURCH-PC-NAME:8000/admin/`
- Kiosk: `http://CHURCH-PC-NAME:8000/kiosk/?kiosk=kiosk1`

To display the computer name, run:

```powershell
hostname
```

## Windows Firewall

Allow Python or TCP port `8000` through Windows Defender Firewall on **Private networks**. Do not expose the port on a public network.

## Installing Updates

### Normal Control Panel Update

Finish check-in on all kiosks first. Open the Control Panel, click **Check for updates**, then **Install Update**. The panel checks GitHub, creates a database backup, stops the server, installs changes from `main`, installs dependencies, applies migrations, collects static files, and restarts the server. A separate manual stop/start is not needed for this path.

If local tracked files differ or the installation is already current, the panel offers a repair/reinstall that replaces tracked application files. Keep intentional local code edits separately before accepting repair. The ignored database, `.env`, media, backups, and logs remain local. On a failed update, the panel attempts to restart a previously running server; it does not roll back code, dependencies, or migrations automatically.

### Manual Recovery When the Panel Is Unavailable

1. Stop the server. Use `Ctrl+C` in its terminal, or identify the process on port 8000:

   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -State Listen |
       Select-Object OwningProcess
   Stop-Process -Id PROCESS_ID
   ```

   Replace `PROCESS_ID` with the Welcome System process ID after confirming it is the correct application.

2. From the project folder, create a database backup with the installed application:

   ```powershell
   cd C:\WelcomeSystem
   .\.venv\Scripts\python.exe manage.py shell -c "from core.backups import create_database_backup; print(create_database_backup(label='before-update').path)"
   ```

   Confirm the backup succeeded before updating. Preserve `.env` and `media/` separately; the database backup does not include them.

3. Download and prepare the update:

   ```powershell
   git pull --ff-only origin main
   powershell.exe -NoProfile -ExecutionPolicy Bypass `
       -File .\scripts\deploy_windows.ps1 `
       -SkipAdminUser -NoStart -WaitAtEnd
   ```

   Stop if either command fails. Resolve the reported issue before starting the updated app.

4. Double-click **Start Welcome System.cmd** to start the server and open the controls. The legacy server-only alternative is:

   ```powershell
   .\scripts\start_windows.cmd
   ```

5. Verify the Admin dashboard and each kiosk, then print a test label from each configured printer.

## Backup and Restore

Database backups live in `backups/`. Use the admin backup page or Control Panel to create them. Restores require a compatible Welcome System schema and migration version; unrelated SQLite files and incompatible versions are rejected. A pre-restore backup is created automatically.

Restore pauses other web requests and clears sessions, so all users must sign in again. If the database is busy, wait for requests to finish and try again. Older backups should be restored with their matching application version in a separate installation, which can then be updated normally.

The independent `maintenance.sqlite3` file coordinates restoration; it is not the application database and must not be selected as a backup. Stop the server before database-changing terminal commands.

## Printer Setup

For Server Printer mode, install the manufacturer's full Windows driver and confirm that a Windows test page prints before configuring Welcome System.

Run the included printer diagnostic:

```powershell
.\scripts\printer_diagnostics_windows.cmd
```

Use the exact Windows printer name shown by the diagnostic in the Server Printer mapping. For example:

```json
{
  "kiosk1": "queue:Brother_QL_820NWB"
}
```

Printer settings are read from the database on requests. Refresh the kiosk and use **Test Printer** after changing them. A printer profile assigned to a kiosk takes priority over the legacy printer mapping; see [Printing](README.md#printing). A “ready” label confirms configuration, not successful physical output.

## Logs

Use **Open Logs Folder** in the Control Panel. Log names depend on how the server was started:

- Launcher or Control Panel: `logs/welcome-system-server.log` and `logs/welcome-system-server-error.log`.
- Manual Windows start script: `logs/waitress-out.log` and `logs/waitress-error.log`.
- Legacy Windows deployment script: `logs/deploy-windows.log`. The new launcher shows setup progress and errors in its terminal window.

Review the error log for the startup method you used if the application does not start.

## Current Security Scope

This deployment is intended for a trusted church local network. Do not forward port `8000` from the internet-facing router. Debug is disabled and explicit allowed hosts are enforced by default. HTTPS gateway setup remains a separate deployment task; the environment switch alone does not install certificates or a reverse proxy.
