# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
- Initial Django scaffold for CATS
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
