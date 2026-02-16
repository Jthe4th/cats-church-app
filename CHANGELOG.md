# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.6.4-alpha] - 2026-02-16
- Added Windows-first production runtime support using Waitress and a new `scripts/run_prod.ps1`.
- Refactored default settings/group seeding from app startup into `post_migrate` to remove startup DB warnings.
- Expanded service-page live polling payload with service metadata (`service_id`, `service_label`, `service_status`).
- Live-refresh now updates both Attendees and First-Time Visitors tables, not just counts.
- Service-page polling now runs every 5 seconds for faster updates during active check-in.
- Added temporary green row highlighting (~5 seconds) for newly added Attendees and First-Time Visitors.
- Ensured kiosk "I'm new here" modal form is reset whenever opened/closed.
- Replaced MIT with a custom non-commercial license and updated README licensing text.

## [0.6.3-alpha] - 2026-02-13
- Rebranded user-facing product name from CATS to Welcome System across docs and UI labels.
- Added `ROADMAP.md` with phased delivery priorities, risks, and decision notes.
- Updated developer guidance to keep internal `CATS_VERSION` while using Welcome System branding.

## [0.6.2-alpha] - 2026-02-13
- Added Church Service status (`open`/`closed`) with admin controls to close/reopen a service.
- Defaulted existing past services to `closed` during migration.
- Added a status toolbar on Manage Church Service with clear open/closed badge and action buttons.
- Added live service dashboard counters for attendees and first-time visitors (auto-refresh every 10s).
- Added live filter search box for the Not checked in / Missing list.
- Blocked kiosk check-in/search when the service is closed and auto-logout kiosks when status changes to closed.
- Added kiosk info menu service line (`Service: ...` or `No service open`) and refined version/logout sizing.
- Disabled Missing-list check-in buttons when managing a closed service (with server-side enforcement).

## [0.6.1-alpha] - 2026-02-13
- Added groups-based kiosk login gate (`Greeter`/`Admin`) and kiosk logout path.
- Added Pastor-only confidential notes field for people records in admin/staff flows.
- Added kiosk modal-based search results and visitor modal flow to avoid kiosk scrolling.
- Added kiosk "check in only" actions (family and visitor) without printing labels.
- Added checked-in state indicators in kiosk results with per-person reprint action.
- Added kiosk search by last name and last 4 phone digits.
- Added info-menu in kiosk header with online/server status polling (15s), version, and logout.
- Added customizable kiosk background colors (light/dark) via system settings.
- Added configurable welcome heading and heading font settings.
- Added Google Fonts support with source controls and curated font list (including Noto fonts).
- Added bulk System Settings editor page and hid regular per-row settings editor in navigation.
- Added admin root redirect so `/admin/` lands on Church Services list after login.

## [0.5-alpha] - 2026-02-11
- Initial Django scaffold for Welcome System
- Core models (Family, Person, Service, Attendance)
- Kiosk check-in flow and label print view
- Bootstrap-based UI and print stylesheet
- Added staff-only people editor with photo upload support
- Branded admin header and shared theme variables for kiosk and staff pages
- On-screen keyboard for kiosk search
- Batch printing with auto-return to kiosk after printing
- Family search results grouped once, with all checkboxes selected by default
- Admin missing members report (latest service)
- Roles via Django Groups (`Greeter`, `Admin`, `Pastor`) and kiosk login gate
- Pastor-only confidential notes on people records
- Kiosk search modal workflow with manual Search click, no-scroll main view, and visitor modal
- Kiosk search by last name and last 4 phone digits
- `Check in only` path (no-print attendance) for search results and new visitor flow
- Already-checked-in indicators in results with per-person `Reprint nametag`
- Admin `/admin/` root redirect to Church Services list after login
- UI/versioning updates: app version now shown in kiosk status and admin header
