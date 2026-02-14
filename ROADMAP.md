# Welcome System Roadmap

## Vision
Welcome System should provide fast, reliable church check-in for kiosks and staff while staying simple to operate on a local network.

## Current State
- Kiosk check-in with greeter login, search, print, and check-in-only flows
- Service open/closed controls with kiosk lockout when closed
- Admin and staff management for people, families, services, and reports
- System settings for kiosk look/feel and label formatting

## Phase 1 (Next 2-4 Weeks)
- **Role hardening + permissions**
  - Enforce clear role boundaries for Greeter, Admin, and Pastor.
- **Audit log**
  - Track check-ins, reprints, settings changes, and service open/close actions.
- **Manual attendance workflow**
  - Add a quick staff flow to mark attendees who did not print a nametag.
- **Printer reliability tools**
  - Add printer test label, media preset checks, and retry guidance.
- **Kiosk resiliency**
  - Improve offline queue visibility and sync status feedback.

## Phase 2 (Next 1-2 Months)
- **Operational service console**
  - Build a dedicated “Today’s Service” screen for staff (counts, search, quick actions).
- **Data quality tools**
  - Add duplicate detection and merge flows for people/families.
  - Add an optional full record deletion flow to permanently remove a person's entire profile and related data.
- **Reporting pack**
  - Weekly/monthly attendance trends, first-time visitor follow-up list, export bundles.
- **Digital outreach lists**
  - Allow staff to add people to church email and/or text messaging lists with clear opt-in tracking.
- **Settings UX improvements**
  - Group settings, add validation helpers, defaults reset, and preview controls.

## Phase 3 (Later)
- **Native kiosk packaging**
  - Evaluate Electron/Tauri for stable silent printing and stronger kiosk lock-down.
- **Security and recovery**
  - Add stronger auth controls and scheduled backup/restore workflows.
- **Multi-service enhancements**
  - Support multiple services per day with clear kiosk/staff service selection.

## Risks / Dependencies
- Old kiosk browsers may require compatibility-safe JS/CSS patterns.
- Printer behavior varies by driver/model and needs real-device validation.
- LAN-only deployment requires stable host uptime and local backup discipline.

## Decision Log
- SQLite remains default for lightweight local deployment.
- Django admin remains core staff management surface for now.
- Kiosk UX prioritizes large touch targets and minimal navigation.
