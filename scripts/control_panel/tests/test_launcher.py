import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

PANEL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PANEL_DIR))
import launch_welcome_system as launcher
from welcome_system_control_panel import ActionResult, WelcomeSystemController


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="welcome space ' ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.controller = WelcomeSystemController(self.root)
        self.python = self.controller.python_path()

    def test_running_server_opens_controls_without_setup_or_restart(self):
        with patch.object(self.controller, "health_check", return_value=True), \
             patch.object(self.controller, "start") as start, \
             patch.object(launcher, "prepare") as prepare, \
             patch.object(launcher, "offer_shortcut") as shortcut, \
             patch.object(launcher, "run") as run:
            self.assertEqual(launcher.launch(self.controller), 0)
        start.assert_not_called()
        prepare.assert_not_called()
        shortcut.assert_called_once_with(self.root, force=False)
        self.assertEqual(run.call_args.args[0][0], self.python)

    def test_ready_installation_starts_before_opening_controls(self):
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        with patch.object(self.controller, "health_check", return_value=False), \
             patch.object(self.controller, "start", return_value=ActionResult(True, "Ready")) as start, \
             patch.object(launcher.subprocess, "run", return_value=Mock(returncode=0)), \
             patch.object(launcher, "prepare") as prepare, \
             patch.object(launcher, "offer_shortcut"), \
             patch.object(launcher, "run") as run:
            self.assertEqual(launcher.launch(self.controller), 0)
        start.assert_called_once()
        prepare.assert_not_called()
        run.assert_called_once()

    def test_declining_setup_does_not_start_or_change_installation(self):
        with patch.object(self.controller, "health_check", return_value=False), \
             patch.object(launcher, "ask", return_value=False), \
             patch.object(launcher, "prepare") as prepare, \
             patch.object(self.controller, "start") as start:
            self.assertEqual(launcher.launch(self.controller), 0)
        prepare.assert_not_called()
        start.assert_not_called()

    def test_failed_start_does_not_open_panel_or_offer_shortcut(self):
        with patch.object(self.controller, "health_check", return_value=False), \
             patch.object(launcher, "ask", return_value=True), \
             patch.object(launcher, "prepare"), \
             patch.object(self.controller, "start", return_value=ActionResult(False, "Port busy")), \
             patch.object(launcher, "offer_shortcut") as shortcut, \
             patch.object(launcher, "run") as run:
            self.assertEqual(launcher.launch(self.controller), 1)
        shortcut.assert_not_called()
        run.assert_not_called()

    def test_setup_refuses_busy_port_before_changes(self):
        with patch.object(launcher, "port_in_use", return_value=True), \
             patch.object(launcher, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Stop the server"):
                launcher.prepare(self.controller)
        run.assert_not_called()

    def test_setup_stops_on_dependency_failure(self):
        with patch.object(launcher, "port_in_use", return_value=False), \
             patch.object(launcher, "run", side_effect=subprocess.CalledProcessError(1, "venv")), \
             patch.object(launcher, "backup_before_setup") as backup:
            with self.assertRaises(subprocess.CalledProcessError):
                launcher.prepare(self.controller)
        backup.assert_not_called()

    def test_backup_includes_committed_wal_data(self):
        db = sqlite3.connect(self.root / "cats.sqlite3")
        self.addCleanup(db.close)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE example (name TEXT)")
        db.execute("INSERT INTO example VALUES ('Preserved')")
        db.commit()
        launcher.backup_before_setup(self.root)
        saved = next((self.root / "backups").glob("*.sqlite3"))
        with sqlite3.connect(saved) as copy:
            self.assertEqual(copy.execute("SELECT name FROM example").fetchone()[0], "Preserved")

    @unittest.skipIf(sys.platform == "win32", "Mac shell shortcut test")
    def test_mac_shortcut_handles_spaces_quotes_and_arguments(self):
        target = self.root / "Start Welcome System.command"
        target.write_text('#!/bin/bash\nprintf "%s" "$1"\n')
        desktop = self.root / "Desktop"
        launcher.create_shortcut(self.root, desktop=desktop)
        shortcut = desktop / "Welcome System.command"
        result = subprocess.run(["bash", str(shortcut), "argument with spaces"], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "argument with spaces")
        with self.assertRaises(FileExistsError):
            launcher.create_shortcut(self.root, desktop=desktop)

    def test_declined_shortcut_is_not_offered_every_launch(self):
        with patch.object(launcher, "ask", return_value=False) as ask:
            launcher.offer_shortcut(self.root)
            launcher.offer_shortcut(self.root)
        ask.assert_called_once()

    def test_setup_backs_up_before_migrations_and_keeps_existing_admin(self):
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        operations = []
        with patch.object(launcher, "port_in_use", return_value=False), \
             patch.object(launcher, "run", side_effect=lambda command, root: operations.append(command)), \
             patch.object(launcher, "backup_before_setup", side_effect=lambda root: operations.append("backup")), \
             patch.object(launcher.subprocess, "run", return_value=Mock(returncode=0)):
            launcher.prepare(self.controller)
        migration = next(i for i, command in enumerate(operations) if isinstance(command, list) and "migrate" in command)
        self.assertLess(operations.index("backup"), migration)
        self.assertFalse(any(isinstance(command, list) and "createsuperuser" in command for command in operations))

    def test_setup_creates_admin_only_when_missing(self):
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        with patch.object(launcher, "port_in_use", return_value=False), \
             patch.object(launcher, "run") as run, \
             patch.object(launcher, "backup_before_setup"), \
             patch.object(launcher.subprocess, "run", return_value=Mock(returncode=1)):
            launcher.prepare(self.controller)
        self.assertEqual(run.call_args.args[0][-1], "createsuperuser")

    def test_shortcut_failure_still_opens_running_system_controls(self):
        with patch.object(self.controller, "health_check", return_value=True), \
             patch.object(launcher, "ask", return_value=True), \
             patch.object(launcher, "create_shortcut", side_effect=PermissionError("Desktop unavailable")), \
             patch.object(launcher, "run") as run:
            self.assertEqual(launcher.launch(self.controller), 0)
        run.assert_called_once()
        self.assertFalse((self.root / "logs/desktop-shortcut-offered").exists())

    def test_autostart_is_offered_after_setup_and_failure_keeps_panel_available(self):
        with patch.object(self.controller, "health_check", return_value=False), \
             patch.object(launcher, "ask", return_value=True) as ask, \
             patch.object(launcher, "prepare"), \
             patch.object(self.controller, "start", return_value=ActionResult(True, "Ready")), \
             patch.object(launcher, "offer_shortcut"), \
             patch.object(launcher, "run", side_effect=[subprocess.CalledProcessError(1, "autostart"), None]) as run:
            self.assertEqual(launcher.launch(self.controller), 0)
        self.assertEqual(ask.call_count, 2)
        self.assertIn("INSTALL_AUTOSTART", str(run.call_args_list[0].args[0][-1]))
        self.assertIn("welcome_system_control_panel.py", str(run.call_args_list[-1].args[0][-1]))
