# Repository Guidelines
Current version: `0.6.3-alpha`

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
- `core/` — main app models, admin, and kiosk views
- `templates/` — server-rendered HTML templates
- `static/` — CSS assets (including label print styles)
- `manage.py` — Django CLI entrypoint
- `requirements.txt` — Python dependencies

## Build, Test, and Development Commands
- `python3 -m venv .venv` — create a virtual environment on macOS/Linux (`python` on Windows)
- `.venv\Scripts\activate` — activate on Windows PowerShell
- `pip install -r requirements.txt` — install dependencies
- `python3 manage.py migrate` — create/update the SQLite database on macOS/Linux
- `python3 manage.py createsuperuser` — create an admin user on macOS/Linux
- `python3 manage.py runserver 0.0.0.0:8000` — run locally on the network on macOS/Linux
- Prefer `.venv/bin/python manage.py ...` on macOS if `python`/`python3` shell mapping is inconsistent.
- Use `runserver` with auto-reload by default; avoid `--noreload` unless explicitly requested for debugging.

## Core Workflows
- Kiosk check-in: greeter login -> search (last name or last 4 phone digits) -> select family members -> print or check in only
- Service control: staff can close/reopen a service from Manage Church Service; closed services block kiosk check-in
- Attendance tracking: one attendance record per person per service
- Staff management: CRUD for families, people, services, attendance via Django admin
- Kiosk batch print: select multiple people (family group) and print all nametags

## Roles and Usage
- Kiosk devices (3-4): full-screen browser locked to the check-in page (`/kiosk/`)
- Staff laptops (1-2): admin access at `/admin/` for records, families, and attendance
- Optional staff UI: `/staff/people/` for a friendly person profile editor (login required)
- Groups: `Greeter`, `Admin`, `Pastor` (kiosk access requires Greeter/Admin; confidential notes are Pastor-only)

## Current URLs
- Kiosk: `/kiosk/`
- Admin: `/admin/`
- Staff editor: `/staff/people/`
- Missing members report: `/admin/missing-members/`
- Bulk system settings: `/admin/core/systemsetting/bulk/`

## Data Model Notes
- People can belong to a Family (optional) to track households.
- Attendance links a Person to a Service (one per service).
- Services include a status (`open` or `closed`); past services default to `closed`.
- Person fields include name (with middle initial), address, email, phone, birth month/day, and an optional photo file.

## UI and Accessibility
- Large text, high contrast, and oversized touch targets for older users.
- Single-screen primary flow; avoid multi-step wizards.
- Bootstrap is used via CDN for rapid, consistent UI.
- Kiosk uses an on-screen keyboard with letters + number row.
- Admin report: missing members for latest service at `/admin/missing-members/`.

## Kiosk UX Rules
- Search by last name or last 4 phone digits.
- Search results are shown in a modal after pressing Search.
- Keep results grouped by family and pre-check all members.
- Show already-checked-in members with a visual status and allow reprint.
- Disable “Check in only” when the full family is already checked in.
- Open “I'm new here 🙂” as a modal instead of inline form.
- If current service is closed, kiosk auto-logs out and check-in/search actions are blocked.

## Printing and Label Size
- Print view uses `static/css/print.css` with `@page` sizing.
- Update the label size once the printer model is confirmed.
- Printing is triggered by the browser using `window.print()`.
- Batch print uses one label per page and auto-returns to `/kiosk/` after printing.
- Kiosk supports iframe print mode and Chrome kiosk printing flow.
- System settings control label font family/source, first/last name colors, and optional last-name hiding.

## Coding Style & Naming Conventions
- Python: 4-space indentation, snake_case functions/variables, PascalCase classes
- Django templates: keep markup accessible and touch-friendly (large labels/buttons)
- CSS: use kebab-case class names and keep print styles in `static/css/print.css`

## Testing Guidelines
Tests are not configured yet. When added, prefer Django's built-in test runner and place tests in `core/tests.py` or `core/tests/`.

## Commit & Pull Request Guidelines
- Prefer Conventional Commits (e.g., `feat: add attendance kiosk flow`)
- Keep commits small and focused
- Pull requests should include a clear description, steps to verify, and screenshots for UI changes

## Configuration & Secrets
- The database is stored in `cats.sqlite3`
- If environment variables are added, store local values in `.env` and provide `.env.example`

## Roadmap (Near-Term)
- Confirm Brother printer model and set exact label size
- Add family assignment in kiosk flow (optional)
- Add service selection when multiple services per week are introduced

## Roadmap (Packaging + Silent Print)
Browsers cannot reliably bypass the print dialog, so true silent printing requires a native wrapper.

Option A: Electron (recommended)
- Run Django locally and open `http://127.0.0.1:8000/kiosk/` in an Electron window.
- On “Print Nametags”, send a message to Electron to print silently via `webContents.print({ silent: true, deviceName: "Brother..." })`.
- Use a hidden window for `/print-batch/?ids=...` so labels print without showing the page.
- Package for Windows/macOS (larger installer size, most reliable printing).

Option B: Tauri (smaller)
- Similar flow, but printing APIs are less mature than Electron.
- Use if smaller installer size matters more than printing reliability.

Future Enhancements
- Add `/api/print-job/` endpoint so the native wrapper can trigger print jobs directly.
- Add printer configuration UI (select printer, label size).
- Add an on-screen “Exit kiosk” helper that explains how to safely exit Chrome kiosk mode when no keyboard is available (e.g., prompt staff to plug in a keyboard or use OS-level kiosk escape).
