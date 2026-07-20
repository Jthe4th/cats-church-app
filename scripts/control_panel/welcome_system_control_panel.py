#!/usr/bin/env python3
"""Cross-platform staff control panel for Welcome System.

Run through an OPEN_WELCOME_SYSTEM_CONTROL_PANEL launcher after one-time setup.
It can also be started directly with the project's virtual-environment Python:
`.venv/bin/python scripts/control_panel/welcome_system_control_panel.py` on macOS/Linux
or `.venv\\Scripts\\python.exe scripts\\control_panel\\welcome_system_control_panel.py` on Windows.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIRECTORY = PROJECT_ROOT / "logs"
PID_PATH = LOG_DIRECTORY / "welcome-system-server.pid"
OUTPUT_LOG_PATH = LOG_DIRECTORY / "welcome-system-server.log"
ERROR_LOG_PATH = LOG_DIRECTORY / "welcome-system-server-error.log"
DEFAULT_PORT = 8000


@dataclass(frozen=True)
class ActionResult:
    success: bool
    message: str


class WelcomeSystemController:
    def __init__(self, project_root: Path = PROJECT_ROOT, port: int = DEFAULT_PORT):
        self.project_root = project_root
        self.port = port
        self.log_directory = project_root / "logs"
        self.pid_path = self.log_directory / "welcome-system-server.pid"
        self.output_log_path = self.log_directory / "welcome-system-server.log"
        self.error_log_path = self.log_directory / "welcome-system-server-error.log"

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def admin_url(self) -> str:
        return f"{self.local_url}/admin/"

    @property
    def kiosk_url(self) -> str:
        return f"{self.local_url}/kiosk/?kiosk=kiosk1"

    @property
    def lan_host(self) -> str:
        return socket.gethostname()

    @property
    def lan_kiosk_url(self) -> str:
        return f"http://{self.lan_host}:{self.port}/kiosk/?kiosk=kiosk1"

    def python_path(self) -> Path:
        relative_path = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
        return self.project_root / relative_path

    def health_check(self, timeout: float = 1.5) -> bool:
        try:
            with urllib.request.urlopen(f"{self.local_url}/healthz/", timeout=timeout) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def status(self) -> ActionResult:
        if self.health_check():
            return ActionResult(True, f"Welcome System is running. Kiosk: {self.lan_kiosk_url}")
        return ActionResult(False, "Welcome System is not running.")

    def start(self) -> ActionResult:
        if self.health_check():
            return ActionResult(True, "Welcome System is already running.")

        python = self.python_path()
        if not python.exists():
            return ActionResult(False, "Setup is incomplete. Run the deployment/setup instructions first.")

        self.log_directory.mkdir(parents=True, exist_ok=True)
        try:
            with self.output_log_path.open("ab") as output_log, self.error_log_path.open("ab") as error_log:
                kwargs: dict = {
                    "cwd": self.project_root,
                    "stdin": subprocess.DEVNULL,
                    "stdout": output_log,
                    "stderr": error_log,
                }
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                else:
                    kwargs["start_new_session"] = True
                process = subprocess.Popen(
                    [str(python), "-m", "waitress", f"--listen=0.0.0.0:{self.port}", "cats.wsgi:application"],
                    **kwargs,
                )
        except OSError as exc:
            return ActionResult(False, f"Could not start Welcome System: {exc}")

        self.pid_path.write_text(str(process.pid), encoding="ascii")
        for _ in range(15):
            time.sleep(1)
            if self.health_check():
                return ActionResult(True, f"Welcome System is ready. Kiosk: {self.lan_kiosk_url}")
            if process.poll() is not None:
                self.pid_path.unlink(missing_ok=True)
                return ActionResult(False, self._start_failure_message())
        return ActionResult(False, self._start_failure_message())

    def stop(self) -> ActionResult:
        if not self.health_check():
            self.pid_path.unlink(missing_ok=True)
            return ActionResult(True, "Welcome System is already stopped.")

        pids = self._listening_pids()
        if not pids:
            pid = self._recorded_pid()
            if pid and self._process_exists(pid):
                pids = [pid]
        if not pids:
            return ActionResult(False, "Welcome System is running, but its server process could not be found.")

        try:
            for pid in pids:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=True, capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
        except (OSError, subprocess.CalledProcessError) as exc:
            return ActionResult(False, f"Could not stop Welcome System: {exc}")

        for _ in range(10):
            time.sleep(0.5)
            if not self.health_check():
                self.pid_path.unlink(missing_ok=True)
                return ActionResult(True, "Welcome System has stopped.")
        return ActionResult(False, "The server did not stop. See the Control Panel guide for help.")

    def restart(self) -> ActionResult:
        stopped = self.stop()
        if not stopped.success:
            return stopped
        return self.start()

    def create_backup(self) -> ActionResult:
        python = self.python_path()
        if not python.exists():
            return ActionResult(False, "Setup is incomplete. Run the deployment/setup instructions first.")
        command = (
            "from core.backups import create_database_backup; "
            "backup = create_database_backup(label='control-panel'); print(backup.path)"
        )
        completed = subprocess.run(
            [str(python), "manage.py", "shell", "-c", command],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            return ActionResult(False, f"Backup failed. See {self.error_log_path.name} or run the setup check.")
        backup_path = completed.stdout.strip().splitlines()[-1]
        return ActionResult(True, f"Backup created: {backup_path}")

    def update(self) -> ActionResult:
        python = self.python_path()
        if not python.exists():
            return ActionResult(False, "Setup is incomplete. Run the deployment/setup instructions first.")
        backup = self.create_backup()
        if not backup.success:
            return backup
        stopped = self.stop()
        if not stopped.success:
            return stopped

        steps = [
            ["git", "pull", "--ff-only", "origin", "main"],
            [str(python), "-m", "pip", "install", "-r", "requirements.txt"],
            [str(python), "manage.py", "migrate"],
            [str(python), "manage.py", "collectstatic", "--noinput"],
        ]
        for command in steps:
            completed = subprocess.run(command, cwd=self.project_root, capture_output=True, text=True)
            if completed.returncode:
                detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
                return ActionResult(False, f"Update failed during {' '.join(command[:3])}. {' '.join(detail)}")
        return self.start()

    def open_logs(self) -> ActionResult:
        self.log_directory.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(self.log_directory)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.log_directory)])
            else:
                subprocess.Popen(["xdg-open", str(self.log_directory)])
        except OSError as exc:
            return ActionResult(False, f"Could not open the logs folder: {exc}")
        return ActionResult(True, "Opened the logs folder.")

    def _start_failure_message(self) -> str:
        return f"Welcome System did not start. Open {self.error_log_path.name} in the logs folder for details."

    def _recorded_pid(self) -> int | None:
        try:
            return int(self.pid_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None

    def _listening_pids(self) -> list[int]:
        """Return process IDs listening on this panel's configured TCP port."""
        try:
            if os.name == "nt":
                completed = subprocess.run(
                    ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False
                )
                pids = []
                for line in completed.stdout.splitlines():
                    columns = line.split()
                    if len(columns) < 5 or columns[0].upper() != "TCP" or columns[3].upper() != "LISTENING":
                        continue
                    if columns[1].rsplit(":", 1)[-1] == str(self.port):
                        pids.append(int(columns[4]))
                return sorted(set(pids))

            completed = subprocess.run(
                ["lsof", "-t", f"-iTCP:{self.port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                check=False,
            )
            return sorted({int(pid) for pid in completed.stdout.split() if pid.isdigit()})
        except (OSError, ValueError):
            return []

    @staticmethod
    def _process_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


class ControlPanelWindow:
    def __init__(self, controller: WelcomeSystemController):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("Welcome System Control Panel")
        self.root.minsize(560, 410)
        self.root.resizable(False, False)
        self.status_text = tk.StringVar(value="Checking server status...")
        self.status_color = tk.StringVar(value="#6c757d")
        self._build(ttk)
        self.refresh_status()

    def _build(self, ttk):
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Welcome System Control Panel", font=("Arial", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Use this window to run the church check-in server.").pack(anchor="w", pady=(4, 18))

        status_frame = ttk.LabelFrame(frame, text="Server status", padding=14)
        status_frame.pack(fill="x")
        self.status_label = self.tk.Label(
            status_frame,
            textvariable=self.status_text,
            anchor="w",
            justify="left",
            wraplength=500,
            fg=self.status_color.get(),
            font=("Arial", 11, "bold"),
        )
        self.status_label.pack(fill="x")
        ttk.Button(status_frame, text="Refresh status", command=self.refresh_status).pack(anchor="w", pady=(10, 0))

        server_frame = ttk.LabelFrame(frame, text="Weekly server controls", padding=12)
        server_frame.pack(fill="x", pady=(16, 0))
        self._button_row(
            server_frame,
            [
                ("Start Welcome System", self.start, "start"),
                ("Stop Welcome System", self.stop, "stop"),
                ("Restart", self.restart),
            ],
        )

        helpful_frame = ttk.LabelFrame(frame, text="Helpful actions", padding=12)
        helpful_frame.pack(fill="x", pady=(16, 0))
        self._button_row(helpful_frame, [("Open Admin", lambda: webbrowser.open(self.controller.admin_url)), ("Open Kiosk 1", lambda: webbrowser.open(self.controller.kiosk_url)), ("Create Backup", self.create_backup)])
        self._button_row(helpful_frame, [("Install Update", self.update), ("Open Logs Folder", self.open_logs)])

        ttk.Label(
            frame,
            text="For kiosk devices, use the LAN address shown in Server status. Do not close this panel while an update is running.",
            wraplength=510,
        ).pack(anchor="w", pady=(18, 0))

    def _button_row(self, parent, buttons):
        row = self.ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        button_colors = {
            "start": ("#198754", "#146c43"),
            "stop": ("#dc3545", "#b02a37"),
        }
        for button in buttons:
            text, command, *kind = button
            if kind:
                background, active_background = button_colors[kind[0]]
                self._colored_action_button(row, text, command, background, active_background).pack(side="left", padx=(0, 8))
            else:
                self.ttk.Button(row, text=text, command=command).pack(side="left", padx=(0, 8))

    def _colored_action_button(self, parent, text, command, background, active_background):
        """Use a label so action colors render consistently on macOS Tk."""
        button = self.tk.Label(
            parent,
            text=text,
            background=background,
            foreground="white",
            font=("Arial", 11, "bold"),
            padx=16,
            pady=9,
            cursor="hand2",
            takefocus=True,
        )

        def activate(_event=None):
            command()

        button.bind("<Button-1>", activate)
        button.bind("<Return>", activate)
        button.bind("<space>", activate)
        button.bind("<Enter>", lambda _event: button.configure(background=active_background))
        button.bind("<Leave>", lambda _event: button.configure(background=background))
        return button

    def _run(self, action, confirm: str | None = None, show_error: bool = True):
        if confirm and not self.messagebox.askyesno("Please confirm", confirm):
            return
        self.status_text.set("Working...")
        self.status_label.configure(fg="#6c757d")

        def worker():
            result = action()
            self.root.after(0, lambda: self._show_result(result, show_error))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, result: ActionResult, show_error: bool = True):
        self.status_text.set(result.message)
        self.status_label.configure(fg="#198754" if result.success else "#b02a37")
        if show_error and not result.success:
            self.messagebox.showerror("Welcome System", result.message)

    def refresh_status(self):
        self._run(self.controller.status, show_error=False)

    def start(self):
        self._run(self.controller.start)

    def stop(self):
        self._run(self.controller.stop, "Stop Welcome System for every kiosk and staff device?")

    def restart(self):
        self._run(self.controller.restart, "Restart Welcome System for every kiosk and staff device?")

    def create_backup(self):
        self._run(self.controller.create_backup)

    def update(self):
        self._run(self.controller.update, "Install the latest approved update from GitHub and restart the server?")

    def open_logs(self):
        self._run(self.controller.open_logs)

    def run(self):
        self.root.mainloop()


def run_terminal_menu(controller: WelcomeSystemController) -> int:
    actions = {
        "1": ("Start Welcome System", controller.start),
        "2": ("Stop Welcome System", controller.stop),
        "3": ("Restart Welcome System", controller.restart),
        "4": ("Open Admin", lambda: ActionResult(webbrowser.open(controller.admin_url), "Opened Admin.")),
        "5": ("Open Kiosk 1", lambda: ActionResult(webbrowser.open(controller.kiosk_url), "Opened Kiosk 1.")),
        "6": ("Create Backup", controller.create_backup),
        "7": ("Install Update", controller.update),
        "8": ("Open Logs Folder", controller.open_logs),
        "9": ("Refresh Status", controller.status),
    }
    while True:
        print("\nWelcome System Control Panel")
        for key, (label, _action) in actions.items():
            print(f"  {key}. {label}")
        print("  Q. Quit")
        choice = input("Choose an action: ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            return 0
        action = actions.get(choice)
        if not action:
            print("Please choose a listed number.")
            continue
        result = action[1]()
        print(result.message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Welcome System cross-platform control panel")
    parser.add_argument("--start-server", action="store_true", help="Start the server without opening the window")
    parser.add_argument("--stop-server", action="store_true", help="Stop the server without opening the window")
    parser.add_argument("--status", action="store_true", help="Print server status without opening the window")
    arguments = parser.parse_args()
    controller = WelcomeSystemController()

    for requested, action in [
        (arguments.start_server, controller.start),
        (arguments.stop_server, controller.stop),
        (arguments.status, controller.status),
    ]:
        if requested:
            result = action()
            print(result.message)
            return 0 if result.success else 1

    try:
        import tkinter
    except ImportError as exc:
        print(f"Desktop window unavailable ({exc}). Opening the terminal Control Panel instead.")
        return run_terminal_menu(controller)
    try:
        ControlPanelWindow(controller).run()
    except tkinter.TclError as exc:
        print(f"Desktop window unavailable ({exc}). Opening the terminal Control Panel instead.")
        return run_terminal_menu(controller)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
