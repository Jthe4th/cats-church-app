# Welcome System Leader Guide

This guide is for starting the Welcome System on Sabbath and getting the three kiosks ready for check-in.

The system is already installed on the local server computer. These steps assume you are only starting it and opening the kiosks.

## Morning Startup Checklist

1. Turn on the server computer.
2. Make sure the server computer is connected to the church network.
3. Start the Welcome System server.
4. Open all three kiosk screens.
5. Log in to each kiosk with the Greeter account.
6. Print one test name tag if printers are being used.

## Start The Server

On the server computer, open the Welcome System project folder.

If there is a saved startup shortcut or script, use that first.

If you need to start it manually, open Terminal or PowerShell in the project folder and run:

```bash
.venv/bin/python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
```

On Windows, the command may be:

```powershell
python -m waitress --listen=0.0.0.0:8000 cats.wsgi:application
```

Leave that window open while the system is in use.

To stop the server later, click in that window and press:

```text
Ctrl+C
```

## Open The Admin Page

On the server computer, open:

```text
http://127.0.0.1:8000/admin/
```

Use the admin page to confirm the current church service is open.

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

After each kiosk opens once with its kiosk ID, Chrome should remember that ID.

## Confirm Each Kiosk Is Ready

On each kiosk:

1. Log in with a Greeter account.
2. Tap the small info button in the top corner.
3. Confirm it says `Server online`.
4. Confirm it shows the correct kiosk ID, such as `Kiosk: kiosk1`.
5. Confirm it says `PrintNode: ready` if PrintNode printing is being used.
6. Confirm the correct service is shown.

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

If printing fails, the kiosk should show an error message.

## Connected Printer Printing

If Connected Printer mode is turned on, Chrome may show a print window or use the local printer attached to that kiosk.

This is the older browser-based print method.

## During Check-In

For existing people:

1. Search by last name or last 4 phone digits.
2. Select the correct person or family members.
3. Tap `Print Nametags` or `Check in only`.

For visitors:

1. Tap `I'm new here`.
2. Enter their name.
3. Tap `Print Name Tag` or `Check in only`.

## Closing Or Reopening A Service

Use the admin page:

```text
http://127.0.0.1:8000/admin/
```

Go to `Church Services`, open the current service, and use the service controls.

If the service is closed, kiosks will not allow check-in.

## Shutdown Checklist

1. Close or finish the current service if needed.
2. Close the browser on each kiosk.
3. Stop the server by pressing `Ctrl+C` in the server window.
4. Leave the server computer on or shut it down according to church procedure.

## Quick Troubleshooting

If a kiosk cannot load the page:

- Make sure the server computer is on.
- Make sure the server command is still running.
- Make sure the kiosk is on the church network.
- Check that the kiosk is using `http://SERVER-IP:8000/kiosk/`, not `0.0.0.0`.

If login shows a security or CSRF error:

- Reload the kiosk login page.
- Make sure the address does not use `0.0.0.0`.
- Use the server IP address, such as `http://192.168.1.10:8000/kiosk/?kiosk=kiosk1`.

If printing does not work:

- Tap the kiosk info button and confirm the kiosk ID is shown.
- Confirm the printer is on and has labels.
- If using PrintNode, confirm PrintNode is running on the printer computer.
- Try a different kiosk only if needed.

If the wrong printer prints:

- Check the kiosk ID in the info box.
- Make sure kiosk 1 uses `kiosk1`, kiosk 2 uses `kiosk2`, and kiosk 3 uses `kiosk3`.
