# Windows Deployment

These instructions deploy Welcome System on the church Windows PC and make it available to other devices on the local network.

Repository: <https://github.com/Jthe4th/cats-church-app>

## Requirements

Install the following on the Windows PC:

1. Python 3.12 or newer from <https://www.python.org/downloads/windows/>.
   Select **Add Python to PATH** during installation.
2. Git for Windows from <https://git-scm.com/download/win>.
3. The full Windows driver for each label printer.

The PC and label printers should be connected to the same local network.

## First Installation

Open PowerShell and run:

```powershell
cd C:\
git clone https://github.com/Jthe4th/cats-church-app.git WelcomeSystem
cd C:\WelcomeSystem
.\scripts\deploy_windows.cmd
```

The deployment script will:

- Create a Python virtual environment.
- Install the required packages.
- Apply database migrations.
- Offer to create an administrator account.
- Collect static files.
- Check the application configuration.
- Start the Waitress web server.

Keep the server PC powered on while the kiosk is being used.

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

### 1. Stop the server

Find the process listening on port `8000`:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
    Select-Object OwningProcess
```

Stop the process, replacing `PROCESS_ID` with the displayed number:

```powershell
Stop-Process -Id PROCESS_ID
```

### 2. Back up the database

```powershell
cd C:\WelcomeSystem
New-Item -ItemType Directory -Force backups
Copy-Item cats.sqlite3 "backups\cats-$(Get-Date -Format yyyyMMdd-HHmmss).sqlite3"
```

The application database, uploaded media, backups, virtual environment, and `.env` file are excluded from Git and will not be overwritten by `git pull`.

### 3. Pull and deploy the update

```powershell
git pull --ff-only origin main

powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File .\scripts\deploy_windows.ps1 `
    -SkipAdminUser -NoStart -WaitAtEnd
```

### 4. Restart the application

```powershell
.\scripts\start_windows.cmd
```

Verify that the Admin and Kiosk URLs open after the script reports success.

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

After changing printer configuration, restart the application.

## Logs

Deployment and server logs are stored in:

- `C:\WelcomeSystem\logs\deploy-windows.log`
- `C:\WelcomeSystem\logs\waitress-out.log`
- `C:\WelcomeSystem\logs\waitress-error.log`

Review `waitress-error.log` if the application does not start.

## Current Security Scope

This deployment is intended for a trusted church local network. Do not forward port `8000` from the internet-facing router. Production environment settings and HTTPS should be configured before exposing Welcome System outside the local network.
