# Welcome System Roadmap

Reviewed against `0.9.13-beta` on 2026-09-07. This roadmap separates shipped behavior from proposed work; priorities are planning guidance, not release commitments.

## Vision

Provide fast, reliable church check-in for kiosks and staff while keeping local-network operation simple.

## Shipped

- Greeter/Admin kiosk login, family-grouped search, visitor registration, check-in-only, and label printing.
- Service close/reopen controls and kiosk lockout; one automatic service per local day even when kiosks start together.
- Server validation, atomic visitor/attendance saves, repeat-click protection, and visible submission errors. Check-in requires a live server connection; there is no offline queue.
- Staff/admin people and family management, photo badges, CSV imports, audit logs, and missing-member reports.
- Manage Church Service with 5-second live attendance updates, manual check-in, visitor creation, and attendee/first-time/missing-member tabs and CSV exports.
- Admin dashboard with eight recent services, attendance and first-time counts, member/visitor composition, check-in pace, last check-in, absent-member count, and first-time visitor list.
- Connected Printer, PrintNode, and Server Printer modes, printer profiles, per-kiosk mappings, and test labels.
- Grouped system settings with validation for appearance and printer configuration.
- Windows/Mac Control Panel for start, stop, restart, backups, GitHub update checks, and updates.
- Explicit service-action permissions, installation-specific secret/host configuration, and photo serving with debug disabled.
- Validated database backups/restores with request coordination and session invalidation after restore.

## Next Priorities

### Data quality

- Build a staff workflow for reviewing and merging duplicate people/families. Person pages already show same-last-name candidates, and CSV import matches existing people.
- Design a clearer record-removal workflow explaining effects on attendance, audit history, and uploaded media. Basic Django person deletion already exists.

### Kiosk and printing reliability

- Validate Windows/Mac printer drivers, label rolls, long names, and batch printing on real devices.
- Add durable print-job tracking and explicit retry/reprint handling for uncertain outcomes.
- Add staff visibility into kiosk health and printer failures. Current readiness labels confirm configuration; test prints establish actual printer operation.
- If offline capture is reconsidered, first define reliable persistence, service selection, duplicate prevention, and clear sync/error behavior.

### Staff workflows

- Extend dashboard trends with date filters, period comparisons, and exports. Current charts cover the latest eight service records, not necessarily eight weeks.
- Add contact tracking to the existing first-time visitor list and distinguish returning visitors.
- Add opt-in tracking before building email/text outreach lists.
- Add settings previews, reset-to-default controls, and guided printer discovery/configuration.

## Later

- Explicit kiosk/staff selection among multiple services on the same day. Multiple records are supported today, but the kiosk chooses automatically.
- Optional local HTTPS gateway with a reverse proxy, trusted certificates, and a stable LAN hostname. The app has an HTTPS configuration switch; gateway setup and deployment validation remain future work.
- Scheduled backups, retention, off-machine copies, and recovery drills that include `.env` and `media/`.
- Stronger authentication controls and continued permission regression coverage.
- Optional Electron/Tauri kiosk packaging for kiosk-local printing and lock-down. Managed silent printing already works without a native kiosk wrapper.
- An on-screen exit-kiosk helper for devices without a keyboard.

## Risks and Dependencies

- Older kiosk browsers require compatibility checks.
- Printer behavior varies by model, driver, and media; automated tests do not replace physical test labels.
- LAN operation depends on server uptime, stable allowed host addresses, and backup discipline.
- Bootstrap and optional Google Fonts use external resources; LAN operation does not imply that all visual assets work without internet access.

## Decisions

- SQLite remains the default database for a single server on the local network.
- Django admin remains the main staff management surface.
- Waitress is the production runtime used by the Control Panel on Windows and Mac.
- Large touch targets and minimal navigation remain kiosk priorities.
