# Repository Guidelines

Current version: `0.9.13-beta`

## Project Direction

Welcome System is a lightweight, local-network, web-based check-in system. The primary goals are:

- Fast kiosk check-in (search, confirm, print)
- Reliable attendance history for members and visitors
- Simple staff management via Django admin
- Easy future updates and minimal infrastructure
- Support batch printing for families and a missing-members report for staff

## Naming Note

- Product-facing name is **Welcome System**.
- Internal Django setting key remains `CATS_VERSION` for backward compatibility.

## Project Structure & Module Organization

- `cats/` — Django project settings and routing (`cats/settings.py`, `cats/urls.py`)
- `core/` — models, admin, kiosk views, shared service resolution (`services.py`), backup validation (`backups.py`), and restore coordination (`maintenance.py`)
- `cats/configuration.py` — installation-local `.env` loading and initial secret generation
- `scripts/control_panel/` — Windows/Mac setup and weekly server controls
- `templates/` — server-rendered HTML templates
- `static/` — CSS assets (including label print styles)
- `manage.py` — Django CLI entrypoint
- `requirements.txt` — Python dependencies

## Build, Test, and Development Commands

- `python3 -m venv .venv` — create a virtual environment on macOS/Linux (`python` on Windows)
- `.venv\Scripts\activate` — activate on Windows PowerShell
- `pip install -r requirements.txt` — install dependencies
- `python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application` — recommended production server on Windows
- `python manage.py collectstatic --noinput` — prepare static files for production runtime
- `python3 manage.py migrate` — create/update the SQLite database on macOS/Linux
- `python3 manage.py createsuperuser` — create an admin user on macOS/Linux
- `python3 manage.py runserver 0.0.0.0:8000` — run locally on the network on macOS/Linux
- Prefer `.venv/bin/python manage.py ...` on macOS if `python`/`python3` shell mapping is inconsistent.
- Use `runserver` with auto-reload by default; avoid `--noreload` unless explicitly requested for debugging.

## Core Workflows

- Kiosk check-in: greeter login -> search (last name or last 4 phone digits) -> select family members -> print or check in only
- Service control: staff can close/reopen a service from Manage Church Service; closed services block kiosk check-in
- Attendance tracking: one attendance record per person per service
- Staff management: people/families and service management via Django admin; service deletion is disabled in Manage Church Service. Attendance is managed through the service console.
- Admin landing page: `/admin/` displays the dashboard; open a service for live counts and quick actions.
- Kiosk batch print: select multiple people (family group) and print all nametags
- Manage Church Service auto-refreshes live every 5 seconds (counts, attendees, first-time visitors).

## Roles and Usage

- Kiosk devices (3-4): full-screen browser locked to the check-in page (`/kiosk/`)
- Staff laptops (1-2): admin access at `/admin/` for records, families, and attendance
- Optional staff UI: `/staff/people/` for a friendly person profile editor (login required)
- Groups: `Greeter`, `Admin`, `Pastor` (active users only; kiosk access requires Greeter/Admin; staff/admin access also requires `is_staff`; confidential notes are Pastor-only). Superusers bypass group checks.
- Groups are seeded without model permissions. Configure Django model permissions explicitly. Custom service reads require view/change permission; custom POST actions require `core.change_service`. Configuration, imports, and backups require staff Admin access.

## Current URLs

- Kiosk: `/kiosk/`
- Admin: `/admin/`
- Staff editor: `/staff/people/`
- Missing members report: `/admin/missing-members/`
- Member import: `/admin/member-import/`
- Database backup/restore: `/admin/database-backup/`
- Bulk system settings: `/admin/core/systemsetting/bulk/`

## Data Model Notes

- People can belong to a Family (optional) to track households.
- Attendance links a Person to a Service (one per service).
- Services include a status (`open` or `closed`), defaulting to open. Migration `0008` closed existing past services; new backdated services are not automatically closed.
- `core.services.get_current_service()` uses the configured local date, prefers the latest open same-day service, then the latest same-day service, and creates one only if none exists. The unique nullable `automatic_date` prevents duplicate automatic creation while preserving manual/historical same-day services. Saturday login also uses this resolver.
- Person fields include name (with middle initial), address, email, phone, birth month/day, and an optional photo file.

## UI and Accessibility

- Large text, high contrast, and oversized touch targets for older users.
- Single-screen primary flow; avoid multi-step wizards.
- Bootstrap is used via CDN for rapid, consistent UI.
- Kiosk uses an on-screen keyboard with letters + number row.
- Missing-members report defaults to the latest closed service (or latest service if none is closed), excluding members created after that service date.
- New rows in Attendees/First-Time lists are highlighted briefly to show real-time check-ins.

## Kiosk UX Rules

- Search by last name or last 4 phone digits.
- Search results are shown in a modal after pressing Search.
- Keep results grouped by family and pre-check all members.
- Show already-checked-in members with a visual status and allow reprint.
- Disable both family actions when nobody is selected. Disable “Check in only” when all selected people are already checked in. Never fall back to a primary person for an empty selection.
- Validate visitors on the server and save person, attendance, and audit records in one transaction before printing.
- Require a live server connection; there is no offline submission queue. Disable repeat submissions while saving, show errors, and explain uncertain print outcomes before retrying.
- Open “I'm new here 🙂” as a modal instead of inline form.
- If current service is closed, kiosk auto-logs out and check-in/search actions are blocked.

## Printing and Label Size

- Print view uses `static/css/print.css` with `@page` sizing.
- Configure dimensions in System Settings (defaults: 2.440 × 1.100 inches, 0.100-inch margin, `62red` media). Printer profiles can override managed-printer dimensions. Verify the actual printer/roll with test labels.
- Connected Printer mode uses browser printing (`window.print()`); PrintNode and Server Printer modes submit managed print jobs.
- Batch print uses one label per page and auto-returns to `/kiosk/` after printing.
- Kiosk supports iframe print mode and Chrome kiosk printing flow.
- Kiosk can use global PrintNode or Server Printer mode for silent printing; each kiosk identifies itself with `?kiosk=...` and maps to either a PrintNode printer id through `printnode_printer_map` or an installed queue / LAN printer address through `server_printer_map`. `printer_profiles` and `kiosk_printer_profile_map` take priority when a kiosk has a profile assigned.
- System settings control label font, first/last name colors, and optional last-name hiding. Kiosk heading settings separately control optional Google Font loading.

## Coding Style & Naming Conventions

- Python: 4-space indentation, snake_case functions/variables, PascalCase classes
- Django templates: keep markup accessible and touch-friendly (large labels/buttons)
- CSS: use kebab-case class names and keep print styles in `static/css/print.css`

## Testing Guidelines

Tests use Django's built-in test runner in `core/tests/`; control-panel tests live in `scripts/control_panel/tests/`.

- Run `.venv/bin/python manage.py test core.tests --noinput`.
- Run `.venv/bin/python -m unittest discover -s scripts/control_panel/tests`.
- Check migrations with `.venv/bin/python manage.py makemigrations --check --dry-run`.
- For user-requested UI/text changes, verify the change is actually visible in the rendered page before reporting completion.
- If visibility cannot be verified in-session, explicitly state that and provide the exact manual check performed/needed.

## Commit & Pull Request Guidelines

- Prefer Conventional Commits (e.g., `feat: add attendance kiosk flow`)
- Keep commits small and focused
- Pull requests should include a clear description, steps to verify, and screenshots for UI changes

## Configuration & Secrets

- The application database is `cats.sqlite3`. The separate `maintenance.sqlite3` file coordinates restore access and is not an application backup.
- `.env` holds the installation secret and explicit allowed hosts; environment variables take precedence. Debug defaults to false. See `.env.example`; never commit `.env`.
- `DJANGO_HTTPS=True` enables redirects and secure cookies only after HTTPS is configured. The supported LAN HTTP setup leaves this false.
- Back up before migrations; stop the server before database-changing terminal commands. Restore validates schema/migration compatibility, pauses other web requests, and invalidates sessions. Preserve `media/` and `.env` separately.
- If environment variables are added, store local values in `.env` and provide `.env.example`
- Windows production runtime should use Waitress (`cats.wsgi:application`) rather than Django `runserver`.
- Static assets under Waitress are served via WhiteNoise; run `collectstatic` before production startup.

## Roadmap (Near-Term)

- Validate label sizing and print reliability on installed hardware
- Add family assignment in kiosk flow (optional)
- Add explicit kiosk service selection for multiple same-day services
- Add optional local HTTPS via Caddy reverse proxy (TLS termination in front of Waitress with trusted internal certs and a stable LAN hostname)

## Roadmap (Packaging + Silent Print)

Silent printing already works through PrintNode or Server Printer mode. A native wrapper is a future option for kiosk-local printing and stronger kiosk lock-down. See `ROADMAP.md` for current priorities.

Option A: Electron (future candidate)

- Run Django locally and open `http://127.0.0.1:8000/kiosk/` in an Electron window.
- On “Print Nametags”, send a message to Electron to print silently via `webContents.print({ silent: true, deviceName: "Brother..." })`.
- Use a hidden window for `/print-batch/?ids=...` so labels print without showing the page.
- Package for Windows/macOS (larger installer size, most reliable printing).

Option B: Tauri (future candidate)

- Evaluate printing support and installer size against the deployed printer/OS combinations before choosing a wrapper.

Future Enhancements

- Add `/api/print-job/` endpoint so the native wrapper can trigger print jobs directly.
- Add printer discovery and a guided configuration UI; settings and profile mappings already exist.
- Add an on-screen “Exit kiosk” helper that explains how to safely exit Chrome kiosk mode when no keyboard is available (e.g., prompt staff to plug in a keyboard or use OS-level kiosk escape).
