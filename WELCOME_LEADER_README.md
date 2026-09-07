# Welcome System Leader Guide

For Welcome System `0.9.13-beta`.

This guide is for starting the Welcome System on Sabbath and getting the three kiosks ready for check-in.

The system is already installed on the local server computer. These steps apply to both Mac and Windows servers. If setup is still needed, use [Mac Setup and Usage](MAC_DEPLOYMENT.md) or [Windows Deployment](WINDOWS_DEPLOYMENT.md).

## Morning Startup Checklist

1. Turn on the server computer.
2. Make sure the server computer is connected to the church network.
3. Open the Welcome System Control Panel and confirm the server is running.
4. Open all three kiosk screens.
5. Log in to each kiosk with the Greeter account.
6. Print one test name tag if printers are being used.

## Start The Server

On the server computer, open the Welcome System Control Panel first:

- Windows: double-click `scripts\control_panel\OPEN_WELCOME_SYSTEM_CONTROL_PANEL.cmd`.
- Mac: double-click `scripts/control_panel/OPEN_WELCOME_SYSTEM_CONTROL_PANEL.command` in Finder.

Press **Start Welcome System** if the status does not already say it is running. Use the green status message's kiosk address on the kiosk devices.

If the Control Panel cannot be opened, start the server manually. Open Terminal or PowerShell in the project folder and run:

```bash
.venv/bin/python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
```

On Windows, use the installed virtual environment:

```powershell
.\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
```

Leave that window open while the system is in use. When it was started manually, you can stop it with `Ctrl+C` in that window or with the Control Panel's **Stop Welcome System** button.

If the Control Panel is unavailable, click in the manually started server window and press:

```text
Ctrl+C
```

## Open The Admin Page

On the server computer, open:

```text
http://127.0.0.1:8000/admin/
```

The admin page opens the dashboard. Open **Manage Church Service**, or choose **Church Services** and the current service, to confirm it is open. Closing/reopening requires an account with service-change permission.

Important: do not type `0.0.0.0` in the browser. That address is only used by the server command.

## Open The Three Kiosks

Each kiosk needs its own kiosk ID. This helps the system send labels to the correct printer.

Open these addresses:

```text
http://SERVER-IP:8000/kiosk/?kiosk=kiosk1
```

```text
http://SERVER-IP:8000/kiosk/?kiosk=kiosk2
```

```text
http://SERVER-IP:8000/kiosk/?kiosk=kiosk3
```

Replace `SERVER-IP` with the server computer's network address.

Example:

```text
http://192.168.1.10:8000/kiosk/?kiosk=kiosk1
```

The browser saves the kiosk ID for that address. Reopen the full kiosk URL if the address changes, browser data is cleared, or the ID disappears. If the server address has changed, ask the administrator to update its allowed-host setting too.

## Confirm Each Kiosk Is Ready

On each kiosk:

1. Log in with a Greeter account.
2. Tap the small info button in the top corner.
3. Confirm it says `Server online`.
4. Confirm it shows the correct kiosk ID, such as `Kiosk: kiosk1`.
5. Confirm it says `PrintNode: ready` or `Server Printer: ready` if silent printer mode is being used.
6. Confirm the correct service is shown.

A printer “ready” message means its configuration is present. Use a test label to confirm the printer can actually print.

If a kiosk says `Kiosk: not set`, reopen it with the correct kiosk URL:

```text
http://SERVER-IP:8000/kiosk/?kiosk=kiosk1
```

Use `kiosk2` or `kiosk3` for the other kiosks.

To test that kiosk's printer, tap `Test Printer` in the info box. This prints a test label only. It does not check anyone in.

## PrintNode Printing

If PrintNode printing is turned on, the kiosk should print silently without showing a Chrome print box.

Normal behavior:

- The greeter searches for a person.
- The greeter taps `Print Nametags`.
- The label prints on that kiosk's assigned printer.
- No success popup appears.

If a managed print job fails, the kiosk shows an error and indicates that attendance was saved. Check whether a label already printed before requesting a reprint.

## Server Printer Printing

If Server Printer mode is turned on, the kiosk sends labels to the Welcome System server computer. The server then prints directly to each label printer on the local network.

Normal behavior is the same as PrintNode mode: the greeter taps `Print Nametags`, the assigned printer prints silently, and no Chrome print box appears.

## Connected Printer Printing

If Connected Printer mode is turned on, Chrome may show a print window or use the local printer attached to that kiosk.

This is the browser-based option for a printer connected to the kiosk.

## During Check-In

For existing people:

1. Search by last name or last 4 phone digits.
2. Select the correct person or family members.
3. Tap `Print Nametags` or `Check in only`. Both buttons are disabled if nobody is selected; check-in-only is disabled when all selected people are already checked in.
4. Wait while check-in is saving. The buttons temporarily disable to prevent repeated submissions.

For visitors:

1. Tap `I'm new here`.
2. Enter their first and last names. Phone and email are optional. Correct any validation message before continuing.
3. Tap `Print Name Tag` or `Check in only`.

## Closing Or Reopening A Service

Use the admin page:

```text
http://127.0.0.1:8000/admin/
```

Go to `Church Services`, open the current service, and use the service controls.

If the service is closed, kiosks will not allow check-in and will return to sign-in. After staff reopen it, sign in on each kiosk again.

## Shutdown Checklist

1. Close or finish the current service if needed.
2. Close the browser on each kiosk.
3. In the Control Panel, press **Stop Welcome System**. If the server was started manually and the panel is unavailable, press `Ctrl+C` in its server window.
4. Leave the server computer on or shut it down according to church procedure.

## Backup The Database

Create a backup before service days, before software updates, or before making major changes to people records.

1. Open the admin page.
2. Go to `Database Backup`.
3. Click `Create backup now`.
4. Download the newest backup if you want to copy it to a USB drive or another safe location.

The backup page can also restore a compatible backup. Have the administrator handle restoration: it replaces the database, pauses check-in, and signs everyone out. A pre-restore backup is created first. Backups from a different database version may need a separate matching installation.

Database backups do not include uploaded photos or the server configuration. Ask the administrator to preserve the `media/` folder and `.env` file separately.

## Import A Member List

Use this when you have a spreadsheet of church members to add to the system.

1. Open the admin page.
2. Go to `Import Members`.
3. Download the sample CSV if you need a template.
4. Prepare the spreadsheet with at least `First Name` and `Last Name`.
5. Upload the CSV and click `Preview CSV`.
6. Review warnings or errors.
7. If the preview looks right, upload the same CSV again and click `Import CSV`.

Useful columns include `Family`, `Phone`, `Email`, `Address`, `City`, `State`, `Zip`, `Birth Month`, and `Birth Day`.

## Quick Troubleshooting

If a kiosk cannot load the page:

- Make sure the server computer is on.
- Confirm that the Control Panel says the server is running.
- Make sure the kiosk is on the church network.
- Check that the kiosk is using `http://SERVER-IP:8000/kiosk/`, not `0.0.0.0`.
- If the browser says “Bad Request (400)”, ask the administrator to check that this server IP/name is in `DJANGO_ALLOWED_HOSTS` in `.env`, then restart the server.

If login shows a security or CSRF error:

- Reload the kiosk login page.
- Make sure the address does not use `0.0.0.0`.
- Use the server IP address, such as `http://192.168.1.10:8000/kiosk/?kiosk=kiosk1`.

If check-in cannot be confirmed:

- Keep the form open if the server is offline; check-in is not queued automatically.
- When the connection returns, search again to see whether attendance was recorded before retrying.
- If a print was requested, check the printer before asking for another copy.
- Use **Sign in again** if the kiosk reports an expired session or changed access.
- If database maintenance is in progress, wait until the administrator finishes.

If printing does not work:

- Tap the kiosk info button and confirm the kiosk ID is shown.
- Confirm the printer is on and has labels.
- Confirm the loaded Brother DK label roll matches the label size in System Settings.
- If using PrintNode, confirm PrintNode is running on the printer computer.
- Ask the administrator to check the kiosk’s printer profile or fallback mapping. Server Printer mode may use an installed printer queue or a network address.
- Try a different kiosk only if needed.

If the wrong printer prints:

- Check the kiosk ID in the info box.
- Make sure kiosk 1 uses `kiosk1`, kiosk 2 uses `kiosk2`, and kiosk 3 uses `kiosk3`.
