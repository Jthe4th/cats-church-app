# Welcome System
Version: `0.9.3-beta`

Welcome System is a lightweight, local-network check-in system for churches. It supports kiosk-based sign-in, attendance history, and printable name tags.

Planning and future feature priorities are tracked in `ROADMAP.md`.

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
- Python + Django
- SQLite (local file database)
- Bootstrap (kiosk UI)
- Waitress (recommended production server on Windows)

## Quick Start (Windows)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Open `http://<host-ip>:8000/` on kiosk machines.

## Quick Start (macOS/Linux)
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
- Windows production (PowerShell + Waitress): `scripts\run_prod.ps1`

## Starting/Restarting The Server
- Start (macOS/Linux): `source .venv/bin/activate` then `python3 manage.py runserver 0.0.0.0:8000`
- Start (Windows): `.\.venv\Scripts\activate` then `python manage.py runserver 0.0.0.0:8000`
- Start (Windows production): `.\.venv\Scripts\activate` then `python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application`
- Stop: press `Ctrl+C` in the terminal where the server is running
- Restart: stop with `Ctrl+C`, then run the start command again

Tip (macOS): if shell aliases cause issues, run `.venv/bin/python manage.py runserver 0.0.0.0:8000` directly.

## Printing
Label sizing is controlled in `static/css/print.css`. Batch printing uses one label per page and auto-returns to `/kiosk/` after printing. Update the `@page` size once the printer model is confirmed.

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

On Windows, queue mode renders the label image through the installed Windows printer driver. After updating the app, rerun `scripts\deploy_windows.cmd` so the Windows-only `pywin32` dependency is installed, then restart the app.

Raw network printing is also available by using the printer IP/hostname and raw socket port, usually `9100`:

```json
{
  "kiosk1": "192.168.1.50:9100"
}
```

The kiosk info menu shows the saved kiosk id, printer readiness, and a `Test Printer` button. The test button sends a test label to that kiosk's mapped printer without creating attendance.

Label sizing is configurable in System Settings. Defaults are set for Brother QL 2.4-inch black/red media with a fixed 1.1-inch length (`2.440` in x `1.100` in). The QL-820 series rejects print jobs when the configured label size does not match the installed DK roll.

## Admin
Django admin is available at `/admin/` for managing families, people, services, and attendance.
After login, `/admin/` redirects to Church Services.
System settings are edited in one place at `/admin/core/systemsetting/bulk/`.

## Staff Pages
Staff-only pages (login required) live under `/staff/`, starting with `/staff/people/` for a friendly person editor that supports photo uploads.

## Member Import
Admins can import member records from CSV at `/admin/member-import/`.
The import page includes a sample CSV download and supports columns such as First Name, Last Name, Family, Phone, Email, Address, City, State, Zip, Birth Month, and Birth Day.
Imports preview validation results before saving; existing people are matched by email first, then by first name, last name, and phone.

## Reports
- Missing members report: `/admin/missing-members/` (shows active members without attendance for the latest service)

## Database Backup & Restore
Admins can create, download, upload, and restore SQLite database backups at `/admin/database-backup/`.
Backups are stored locally in the ignored `backups/` folder. A pre-restore backup is created automatically before any restore.

## Media (Photos)
People can have an optional photo file stored under `media/people/photos/`. This is optional and can be used later without changing the data model.

## LAN Deployment
The Django server and SQLite database run on one host machine. All kiosks and staff laptops connect over the church LAN.

Example:
- Server host: `http://192.168.1.10:8000/`
- Kiosks: open `/kiosk/` for check-in
- Staff: open `/admin/` for management

Ensure Windows Firewall allows inbound traffic on the chosen port (default `8000`).

For Windows hosts, prefer Waitress over `runserver` for live church use.

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

For testing, keep the Waitress terminal window open. For always-on operation, run Waitress as a Windows service (NSSM or Task Scheduler).
Static files are served by WhiteNoise under Waitress.

## License
This project uses the **Welcome System Non-Commercial License v1.0**.
Commercial use, sale, or resale is not permitted. See `LICENSE`.
