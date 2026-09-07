# Welcome System

Version: `0.9.13-beta`

Welcome System is a lightweight, local-network check-in system for churches. It supports kiosk-based sign-in, attendance history, and printable name tags.

For weekly operation, use the [Leader Guide](WELCOME_LEADER_README.md). For installation, use [Mac Setup and Usage](MAC_DEPLOYMENT.md) or [Windows Deployment](WINDOWS_DEPLOYMENT.md). The [Control Panel guide](scripts/control_panel/README.md) covers the shared controls. Future work is tracked in the [Roadmap](ROADMAP.md); releases are recorded in the [Changelog](CHANGELOG.md).

## Setup and Usage by Platform

| Task | Mac | Windows |
| --- | --- | --- |
| First-time setup | [Mac installation steps](MAC_DEPLOYMENT.md#first-time-installation) | [Windows installation steps](WINDOWS_DEPLOYMENT.md#first-installation) |
| Open the Control Panel | Double-click `scripts/control_panel/OPEN_WELCOME_SYSTEM_CONTROL_PANEL.command` | Double-click `scripts\control_panel\OPEN_WELCOME_SYSTEM_CONTROL_PANEL.cmd` |
| Start and stop | **Start Welcome System** / **Stop Welcome System** in the panel | Same panel actions |
| Daily check-in | [Leader Guide](WELCOME_LEADER_README.md) | [Leader Guide](WELCOME_LEADER_README.md) |
| Install updates | [Mac updates and recovery](MAC_DEPLOYMENT.md#updates) | [Windows updates and recovery](WINDOWS_DEPLOYMENT.md#installing-updates) |

Install the server on one computer. Other kiosk and staff devices only need a browser and access to that computer's LAN address.

## Highlights

- Kiosk check-in with Greeter login gate
- Search by last name or last 4 phone digits
- Search results shown in a modal for no-scroll kiosk UX
- Check-in without printing (`Check in only`)
- Reprint per checked-in person from search results
- Visitor creation in a modal
- Kiosk info menu with 15-second server health polling
- Attendance tracking by service date
- Staff/admin management via Django admin + staff pages
- Label printing with a dedicated print stylesheet
- On-screen keyboard for kiosk devices
- Batch name tag printing for families
- Bulk system settings editor in admin

## Tech Stack

- Python + Django 5.2 (see `requirements.txt` for dependency ranges)
- SQLite (local file database)
- Bootstrap (kiosk UI)
- Waitress (production server used by the Control Panel on Windows and Mac)

## Installation Configuration

When `.env` is absent and `DJANGO_SECRET_KEY` is not supplied by the environment, the first Django command or server startup creates a private, ignored `.env` file with a random installation secret, debug mode disabled, and explicit local hostnames/IP addresses. Keep this file on the server across restarts and updates. Environment variables override `.env`; see `.env.example` for supported values.

Before connecting LAN kiosks, check `DJANGO_ALLOWED_HOSTS` in `.env` and add the server's LAN IP and hostname (comma-separated, without port numbers). Update this list if the server address changes. `DJANGO_DEBUG=True` is available for local troubleshooting; leave it `False` for church use. Uploaded logos and authorized profile photos are served under Waitress with debug disabled.

Local HTTP remains supported. Enable `DJANGO_HTTPS=True` only after HTTPS is configured; this enables HTTPS redirects and secure session/CSRF cookies. Do not enable it on an HTTP-only installation.

## Development Quick Start (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Open `http://127.0.0.1:8000/kiosk/` locally. Before connecting other devices, add the server address to `DJANGO_ALLOWED_HOSTS` in `.env`. These quick-start commands use the development server; use the Control Panel and Waitress for church services.

## Development Quick Start (macOS/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py runserver 0.0.0.0:8000
```

## Convenience Scripts

Cross-platform helpers that create a venv, install deps, run migrations, and start the server:

- macOS/Linux: `./scripts/run_dev.sh`
- Windows (PowerShell): `scripts\run_dev.ps1`
- Windows Waitress helper: `scripts\run_prod.ps1` (does not collect static files; run `python manage.py collectstatic --noinput` first). For full setup, prefer `scripts\control_panel\SETUP_WELCOME_SYSTEM_WINDOWS.cmd`.

## Easy Weekly Server Controls

Use the tracked [Welcome System Control Panel](scripts/control_panel/README.md) for weekly Start, Stop, Restart, Backup, Update, Admin, Kiosk, and Logs actions on either Windows or Mac. It manages the production Waitress server without staff needing to type commands.

## Manual Server Commands

For normal weekly use, start and stop the server from the [Welcome System Control Panel](scripts/control_panel/README.md). Use these commands only for local development or recovery when the panel is unavailable.

- Development (macOS/Linux): `source .venv/bin/activate` then `python3 manage.py runserver 0.0.0.0:8000`
- Development (Windows): `.\.venv\Scripts\activate` then `python manage.py runserver 0.0.0.0:8000`
- Production (macOS/Linux): `.venv/bin/python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application`
- Production (Windows): `.\.venv\Scripts\activate` then `python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application`
- Stop a manually started server: press `Ctrl+C` in its terminal, or use the Control Panel's **Stop Welcome System** action.
- Restart: stop with `Ctrl+C`, then run the start command again

Tip (macOS): if shell aliases cause issues, run `.venv/bin/python manage.py runserver 0.0.0.0:8000` directly.

## Printing

Configure label dimensions and margins in System Settings. Browser print templates and `static/css/print.css` use those values; managed printer profiles can override them per kiosk. Batch printing uses one label per page and returns to `/kiosk/` after printing. Validate size and alignment with the actual printer and loaded label roll.

Kiosk printing can run in three modes from System Settings:

- `Connected Printer`: current browser-based printing flow.
- `PrintNode Printer`: kiosk check-ins submit a silent PrintNode job instead of opening the browser print dialog.
- `Server Printer`: kiosk check-ins submit a print job from the Django server computer to either an installed printer queue or a raw network printer address.

For PrintNode mode, configure `printnode_api_key` and `printnode_printer_map`. The printer map is JSON that routes each kiosk id to a PrintNode printer id:

```json
{
  "kiosk1": "123456",
  "kiosk2": "123457"
}
```

Open each kiosk with its id once, for example `/kiosk/?kiosk=kiosk1`; the browser stores that id locally and includes it with future kiosk print requests. Staff/admin print pages remain browser-printable as a fallback even when kiosk silent printer mode is enabled.

For a cleaner setup, use `printer_profiles` plus `kiosk_printer_profile_map`. A profile stores the backend, printer target, and optional label calibration in one reusable record:

```json
{
  "front-desk-brother": {
    "backend": "server",
    "target": "queue:Brother_QL_820NWB",
    "label_width_in": "2.440",
    "label_height_in": "1.1",
    "label_margin_in": "0.1",
    "brother_label_media": "62red"
  }
}
```

Then map kiosks to profiles:

```json
{
  "kiosk1": "front-desk-brother"
}
```

Profile mappings take priority. The older `printnode_printer_map` and `server_printer_map` settings remain supported as fallback when a kiosk has no assigned profile.

For Server Printer mode, configure `server_printer_map`. The preferred setup is to route each kiosk id to an installed printer queue on the server computer:

```json
{
  "kiosk1": "queue:Brother_QL_820NWB"
}
```

On Windows, queue mode renders the label image through the installed Windows printer driver. The Control Panel update installs the Windows-only `pywin32` dependency. For manual recovery, stop the server and follow [Windows Deployment](WINDOWS_DEPLOYMENT.md).

Raw network printing is also available by using the printer IP/hostname and raw socket port, usually `9100`:

```json
{
  "kiosk1": "192.168.1.50:9100"
}
```

The kiosk info menu shows the saved kiosk id, printer readiness, and a `Test Printer` button. The test button sends a test label to that kiosk's mapped printer without creating attendance.

Label sizing is configurable in System Settings. Defaults are set for Brother QL 2.4-inch black/red media with a fixed 1.1-inch length (`2.440` in x `1.100` in). The configured media must match the loaded DK roll. Confirm the final size and alignment with a physical test label.

## Admin

Django admin is available at `/admin/` for managing families, people, services, and attendance.
After login, `/admin/` shows the dashboard with service counts, recent attendance trends, check-in pace, and follow-up summaries. Open Manage Church Service for live attendance and quick actions.
System settings are edited in one place at `/admin/core/systemsetting/bulk/`.

## Accounts and Permissions

Migrations create the Greeter, Admin, and Pastor groups. Group creation does not assign Django model permissions automatically. Use a superuser to configure staff accounts and permissions.

- Greeter: kiosk access; staff status is not required.
- Admin: kiosk access; staff status is required for staff pages and configuration, imports, and backups.
- Pastor: staff status is required for staff/admin access; confidential notes are Pastor-only. Pastor membership alone does not grant kiosk access.
- Active staff superusers bypass role checks. Django admin model screens still require their model permissions for ordinary users. Custom service reads require view/change permission, and custom service actions require `core.change_service`.

## Staff Pages

Active staff users in the Admin or Pastor group can use `/staff/people/` for the person editor and photo uploads. `/staff/dashboard/` redirects to the admin dashboard.

## Member Import

Admins can import member records from CSV at `/admin/member-import/`.
The import page includes a sample CSV download and supports columns such as First Name, Last Name, Family, Phone, Email, Address, City, State, Zip, Birth Month, and Birth Day.
Imports preview validation results before saving; existing people are matched by email first, then by first name, last name, and phone.

## Reports

- Missing members report: `/admin/missing-members/` (defaults to the latest closed service, falling back to the latest service when none is closed; supports CSV export). Members created after the selected service date are excluded.

## Database Backup & Restore

Admins can create, download, upload, and restore SQLite database backups at `/admin/database-backup/`.
Backups are stored locally in the ignored `backups/` folder. A pre-restore backup is created automatically before any restore.

## Media (Photos)

Optional profile photos are stored under `media/people/photos/` and appear in staff/admin person and attendance views, with initials as a fallback. Profile images require an authorized signed-in user. Uploaded kiosk logos in `media/branding/` remain available on the sign-in page. Both work with debug mode disabled.

## LAN Deployment

The Django server and SQLite database run on one host machine. All kiosks and staff laptops connect over the church LAN.

Example:

- Server host: `http://192.168.1.10:8000/`
- Kiosks: open `/kiosk/` for check-in
- Staff: open `/admin/` for management

Ensure Windows Firewall allows inbound traffic on the chosen port (default `8000`).

Use Waitress through the Control Panel for live church use on Windows or Mac.

## Windows Production Setup (Waitress)

Use this for church-host deployment and longer runtime stability.

```powershell
cd C:\path\to\cats-app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
```

You can also use:

- `scripts\deploy_windows.cmd` (double-click friendly Windows setup; keeps the PowerShell window open)
- `scripts\deploy_windows.ps1` (full first-time Windows setup, optional admin-user prompt, static files, checks, then starts Waitress)
- `scripts\run_prod.ps1` (sets up venv/dependencies, runs migrations, starts Waitress)

Verification:

- On host machine: `curl -I http://127.0.0.1:8000/admin/`
- On LAN kiosk: open `http://<host-ip>:8000/kiosk/`

Keep a manually started Waitress terminal open while it is in use. Optional sign-in startup is provided by the Control Panel setup guide; it starts the server when the staff account signs in, not before sign-in.
Static files are served by WhiteNoise under Waitress.

## License

This project uses the **Welcome System Non-Commercial License v1.0**.
Commercial use, sale, or resale is not permitted. See `LICENSE`.

## Recovery and Connection Behavior

Backups must match the installed database migration version and contain the required application tables and fields. For an older backup, use its matching Welcome System version in a separate installation, restore there, and then update that installation normally. Database backups do not include the `.env` file or uploaded images; preserve `.env` and `media/` separately.

Restoration waits for active web requests to finish and temporarily blocks new requests. All users must sign in again afterward. The separate `maintenance.sqlite3` file coordinates this across server workers; never upload or restore it as an application backup. Stop the server before running database-changing maintenance commands such as migrations or imports from a terminal.

Kiosk submissions require a live server connection. If a request fails, the form remains available and displays an error. Search again to confirm attendance, and check the printer before requesting another copy when the print outcome is uncertain.

## Verification

Run from the project root after installing requirements:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test core.tests --noinput
.venv/bin/python -m unittest discover -s scripts/control_panel/tests
.venv/bin/python manage.py makemigrations --check --dry-run
```

On Windows, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`. For UI changes, also verify the rendered page in a browser. Physical printer verification is separate from automated tests.
