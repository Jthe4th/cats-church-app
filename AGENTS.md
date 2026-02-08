# Repository Guidelines

## Project Direction
CATS (Church Attendance Tracking System) is a lightweight, local-network, web-based check-in system. The primary goals are:
- Fast kiosk check-in (search, confirm, print)
- Reliable attendance history for members and visitors
- Simple staff management via Django admin
- Easy future updates and minimal infrastructure
 - Support batch printing for families and a missing-members report for staff

## Project Structure & Module Organization
- `cats/` — Django project settings and routing (`cats/settings.py`, `cats/urls.py`)
- `core/` — main app models, admin, and kiosk views
- `templates/` — server-rendered HTML templates
- `static/` — CSS assets (including label print styles)
- `manage.py` — Django CLI entrypoint
- `requirements.txt` — Python dependencies

## Build, Test, and Development Commands
- `python -m venv .venv` — create a virtual environment
- `.venv\Scripts\activate` — activate on Windows PowerShell
- `pip install -r requirements.txt` — install dependencies
- `python manage.py migrate` — create/update the SQLite database
- `python manage.py createsuperuser` — create an admin user
- `python manage.py runserver 0.0.0.0:8000` — run locally on the network

## Core Workflows
- Kiosk check-in: search by first/last name -> select family members -> print labels
- Attendance tracking: one attendance record per person per service
- Staff management: CRUD for families, people, services, attendance via Django admin
 - Kiosk batch print: select multiple people (family group) and print all nametags

## Roles and Usage
- Kiosk devices (3-4): full-screen browser locked to the check-in page (`/kiosk/`)
- Staff laptops (1-2): admin access at `/admin/` for records, families, and attendance
- Optional staff UI: `/staff/people/` for a friendly person profile editor (login required)

## Current URLs
- Kiosk: `/kiosk/`
- Admin: `/admin/`
- Staff editor: `/staff/people/`
- Missing members report: `/admin/missing-members/`

## Data Model Notes
- People can belong to a Family (optional) to track households.
- Attendance links a Person to a Service (one per service).
- Services default to the current date with a simple label (expandable later).
- Person fields include name (with middle initial), address, email, phone, birth month/day, and an optional photo file.

## UI and Accessibility
- Large text, high contrast, and oversized touch targets for older users.
- Single-screen primary flow; avoid multi-step wizards.
- Bootstrap is used via CDN for rapid, consistent UI.
- Kiosk uses an on-screen keyboard for letter-only input.
- Admin report: missing members for latest service at `/admin/missing-members/`.

## Kiosk UX Rules
- Search only by first/last name.
- Auto-search after 3 characters with a short debounce.
- Keep results grouped by family and pre-check all members.
- Hide the visitor form until the “I'm a visitor 🙂” button is used.
- Keep admin access hidden unless the long-press reveal is used.

## Printing and Label Size
- Print view uses `static/css/print.css` with `@page` sizing.
- Update the label size once the printer model is confirmed.
- Printing is triggered by the browser using `window.print()`.
- Batch print uses one label per page and auto-returns to `/kiosk/` after printing.

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
