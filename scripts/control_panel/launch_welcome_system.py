"""Shared setup/start entry point. Uses only the standard library until setup."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shlex
import socket
import sqlite3
import subprocess
import sys

# Keep the Python-version diagnostic usable even with an older system Python.
if sys.version_info < (3, 10):
    if __name__ == "__main__":
        print("Welcome System needs Python 3.10 or newer. Install it from python.org.")
        raise SystemExit(1)
else:
    from welcome_system_control_panel import WelcomeSystemController, PROJECT_ROOT


READINESS_CHECK = """
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cats.settings")
import django, waitress, whitenoise
django.setup()
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.contrib.auth import get_user_model
executor = MigrationExecutor(connection)
if executor.migration_plan(executor.loader.graph.leaf_nodes()):
    print("Database setup or updates are needed.")
    raise SystemExit(1)
if not all((settings.STATIC_ROOT / asset).is_file() for asset in (
    "vendor/bootstrap/bootstrap.min.css", "vendor/bootstrap/bootstrap.bundle.min.js",
    "css/theme.css", "css/kiosk.css",
)):
    print("Local web assets need preparation.")
    raise SystemExit(1)
if not get_user_model().objects.filter(is_superuser=True, is_active=True).exists():
    print("An administrator account needs to be created.")
    raise SystemExit(1)
"""


def ask(question):
    return input(question + " [y/N]: ").strip().lower() in ("y", "yes")


def run(command, root):
    subprocess.run([str(part) for part in command], cwd=root, check=True)


def port_in_use(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def backup_before_setup(root):
    """Use SQLite's backup API, including committed WAL data, before migrations."""
    source = root / "cats.sqlite3"
    if not source.exists() or not source.stat().st_size:
        return
    directory = root / "backups"
    directory.mkdir(exist_ok=True)
    target = directory / ("before-launcher-setup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(target) as backup:
            original.backup(backup)
    print("Database backup saved:", target)


def prepare(controller):
    root = controller.project_root
    python = controller.python_path()
    if port_in_use(controller.port):
        raise RuntimeError("Port 8000 is in use. Stop the server before running setup, then try again.")
    if not python.exists():
        run([sys.executable, "-m", "venv", root / ".venv"], root)
    run([python, "-m", "pip", "install", "-r", root / "requirements.txt"], root)
    # Do not apply migrations to an installation that started during preparation.
    if port_in_use(controller.port):
        raise RuntimeError("The server started during setup. Stop it, then reopen the launcher.")
    backup_before_setup(root)
    run([python, "manage.py", "migrate", "--noinput"], root)
    run([python, "manage.py", "collectstatic", "--noinput"], root)
    run([python, "manage.py", "check"], root)
    admin_check = (
        "from django.contrib.auth import get_user_model; "
        "raise SystemExit(0 if get_user_model().objects.filter("
        "is_superuser=True, is_active=True).exists() else 1)"
    )
    result = subprocess.run([str(python), "manage.py", "shell", "-c", admin_check], cwd=root)
    if result.returncode:
        print("Create the administrator login for this installation.")
        run([python, "manage.py", "createsuperuser"], root)
    print("Setup complete. Before connecting other devices, check DJANGO_ALLOWED_HOSTS in .env.")
    print("Use MAC_DEPLOYMENT.md or WINDOWS_DEPLOYMENT.md for network and printer configuration.")


def create_shortcut(root, desktop=None):
    """Create a shortcut without overwriting an existing desktop item."""
    if os.name == "nt":
        # Environment values avoid interpolating paths into PowerShell source.
        environment = os.environ.copy()
        environment["WELCOME_LAUNCHER"] = str(root / "Start Welcome System.cmd")
        environment["WELCOME_ROOT"] = str(root)
        script = """
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop 'Welcome System.lnk'
if (Test-Path -LiteralPath $path) { throw "Welcome System shortcut already exists: $path" }
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($path)
$link.TargetPath = $env:WELCOME_LAUNCHER
$link.WorkingDirectory = $env:WELCOME_ROOT
$link.Description = 'Start Welcome System and open its controls'
$link.Save()
Write-Output $path
"""
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], env=environment, check=True)
    else:
        desktop = desktop or Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        shortcut = desktop / "Welcome System.command"
        with shortcut.open("x", encoding="utf-8") as output:
            output.write("#!/bin/bash\nexec /bin/bash " + shlex.quote(str(root / "Start Welcome System.command")) + ' "$@"\n')
        shortcut.chmod(0o755)
        print("Desktop shortcut created:", shortcut)


def offer_shortcut(root, force=False):
    marker = root / "logs" / "desktop-shortcut-offered"
    if not force and marker.exists():
        return
    if force or ask("Create a Welcome System shortcut on your desktop?"):
        try:
            create_shortcut(root)
        except (OSError, subprocess.CalledProcessError) as exc:
            print("Could not create the shortcut:", exc)
            print("You can still use Start Welcome System in the project folder.")
            return
    marker.parent.mkdir(exist_ok=True)
    marker.touch()


def launch(controller, shortcut=False):
    root = controller.project_root
    python = controller.python_path()
    setup_completed = False
    if not controller.health_check():
        print("Checking Welcome System setup…")
        ready = False
        if python.exists():
            result = subprocess.run(
                [str(python), "-c", READINESS_CHECK], cwd=root,
                capture_output=True, text=True,
            )
            ready = result.returncode == 0
            if not ready:
                print(result.stdout.strip() or "The environment or application configuration needs attention.")
                if result.stderr.strip():
                    print(result.stderr.strip().splitlines()[-1])
        if not ready:
            print("Setup installs requirements, backs up an existing database, prepares the app, and creates an admin if needed.")
            if not ask("Run setup now?"):
                print("Nothing started. Open this launcher again when you are ready.")
                return 0
            prepare(controller)
            setup_completed = True
        print("Starting Welcome System…")
        result = controller.start()
        print(result.message)
        if not result.success:
            return 1
    else:
        print("Welcome System is already running. Opening its controls.")
    offer_shortcut(root, force=shortcut)
    if setup_completed and ask("Also start the server automatically when you sign in to this computer?"):
        script = root / "scripts/control_panel" / (
            "INSTALL_AUTOSTART_WINDOWS.cmd" if os.name == "nt" else "INSTALL_AUTOSTART_MAC.sh"
        )
        try:
            if os.name == "nt":
                run(["cmd.exe", "/c", str(script)], root)
            else:
                run(["bash", script], root)
        except (OSError, subprocess.CalledProcessError) as exc:
            print("Automatic startup could not be installed:", exc)
            print("The server is running; you can retry using the platform guide.")
    run([python, root / "scripts/control_panel/welcome_system_control_panel.py"], root)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shortcut", action="store_true", help="Create the desktop shortcut even if previously declined")
    args = parser.parse_args()
    try:
        return launch(WelcomeSystemController(), shortcut=args.shortcut)
    except (OSError, RuntimeError, subprocess.CalledProcessError, EOFError, KeyboardInterrupt) as exc:
        print("Welcome System could not finish:", exc)
        print("Fix the reported issue and reopen Start Welcome System. See the platform setup guide if needed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
