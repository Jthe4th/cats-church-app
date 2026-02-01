# CATS — Church Attendance Tracking System

CATS is a lightweight, local-network check-in system for churches. It supports kiosk-based sign-in, attendance tracking, and printable name tags.

## Highlights
- Kiosk check-in (first/last name search)
- Visitor creation on the spot
- Attendance tracking by service date
- Staff management via Django admin
- Label printing with a dedicated print stylesheet
- On-screen keyboard for kiosk devices
- Batch printing for families

## Tech Stack
- Python + Django
- SQLite (local file database)
- Bootstrap (kiosk UI)

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
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

## Convenience Scripts
Cross-platform helpers that create a venv, install deps, run migrations, and start the server:
- macOS/Linux: `./scripts/run_dev.sh`
- Windows (PowerShell): `scripts\run_dev.ps1`

## Printing
Label sizing is controlled in `static/css/print.css`. Batch printing uses one label per page and auto-returns to `/kiosk/` after printing. Update the `@page` size once the printer model is confirmed.

## Admin
Django admin is available at `/admin/` for managing families, people, services, and attendance.

## Staff Pages
Staff-only pages (login required) live under `/staff/`, starting with `/staff/people/` for a friendly person editor that supports photo uploads.

## Reports
- Missing members report: `/admin/missing-members/` (shows active members without attendance for the latest service)

## Media (Photos)
People can have an optional photo file stored under `media/people/photos/`. This is optional and can be used later without changing the data model.

## LAN Deployment
The Django server and SQLite database run on one host machine. All kiosks and staff laptops connect over the church LAN.

Example:
- Server host: `http://192.168.1.10:8000/`
- Kiosks: open `/kiosk/` for check-in
- Staff: open `/admin/` for management

Ensure Windows Firewall allows inbound traffic on the chosen port (default `8000`).
