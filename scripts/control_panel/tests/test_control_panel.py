import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "welcome_system_control_panel.py"
SPEC = importlib.util.spec_from_file_location("welcome_system_control_panel", MODULE_PATH)
control_panel = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = control_panel
SPEC.loader.exec_module(control_panel)


class WelcomeSystemControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.controller = control_panel.WelcomeSystemController(self.project_root, port=8123)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_virtualenv_python(self):
        relative_path = ".venv/Scripts/python.exe" if control_panel.os.name == "nt" else ".venv/bin/python"
        python = self.project_root / relative_path
        python.parent.mkdir(parents=True)
        python.touch()
        return python

    def write_version(self, version="0.9.10-beta"):
        settings_path = self.project_root / "cats" / "settings.py"
        settings_path.parent.mkdir()
        settings_path.write_text(f'CATS_VERSION = "{version}"\n', encoding="utf-8")

    def test_status_reports_lan_kiosk_url_when_healthy(self):
        with patch.object(self.controller, "health_check", return_value=True):
            result = self.controller.status()

        self.assertTrue(result.success)
        self.assertIn("kiosk1", result.message)
        self.assertIn(":8123", result.message)

    def test_start_requires_completed_setup(self):
        with patch.object(self.controller, "health_check", return_value=False):
            result = self.controller.start()

        self.assertFalse(result.success)
        self.assertIn("Setup is incomplete", result.message)

    def test_check_for_updates_reports_when_current_version_is_up_to_date(self):
        self.write_version()
        with patch.object(
            control_panel.subprocess,
            "run",
            side_effect=[Mock(returncode=0), Mock(returncode=0, stdout="0\n")],
        ):
            result = self.controller.check_for_updates()

        self.assertTrue(result.success)
        self.assertIn("0.9.10-beta", result.message)
        self.assertIn("Already up to date", result.message)

    def test_check_for_updates_reports_available_commit_count(self):
        self.write_version("0.9.4-beta")
        with patch.object(
            control_panel.subprocess,
            "run",
            side_effect=[Mock(returncode=0), Mock(returncode=0, stdout="2\n")],
        ):
            result = self.controller.check_for_updates()

        self.assertTrue(result.success)
        self.assertIn("0.9.4-beta", result.message)
        self.assertIn("2 new commits", result.message)

    def test_check_for_updates_uses_github_version_when_git_fetch_fails(self):
        self.write_version("0.9.5-beta")
        response = MagicMock()
        response.read.return_value = b'CATS_VERSION = "0.9.10-beta"\n'
        response.__enter__.return_value = response
        with (
            patch.object(control_panel.subprocess, "run", return_value=Mock(returncode=1, stderr="git unavailable")),
            patch.object(control_panel.urllib.request, "urlopen", return_value=response),
        ):
            result = self.controller.check_for_updates()

        self.assertTrue(result.success)
        self.assertIn("Update available", result.message)
        self.assertIn("latest: 0.9.10-beta", result.message)

    def test_start_launches_waitress_and_records_pid(self):
        python = self.create_virtualenv_python()
        process = Mock(pid=12345)
        process.poll.return_value = None
        with (
            patch.object(self.controller, "health_check", side_effect=[False, True]),
            patch.object(control_panel.subprocess, "Popen", return_value=process) as popen,
            patch.object(control_panel.time, "sleep"),
        ):
            result = self.controller.start()

        self.assertTrue(result.success)
        self.assertEqual(self.controller.pid_path.read_text(encoding="ascii"), "12345")
        self.assertEqual(popen.call_args.args[0][0], str(python))
        self.assertIn("waitress", popen.call_args.args[0])
        self.assertIn("--listen=0.0.0.0:8123", popen.call_args.args[0])

    def test_stop_finds_and_stops_a_manually_started_server(self):
        with (
            patch.object(self.controller, "health_check", side_effect=[True, False]),
            patch.object(self.controller, "_listening_pids", return_value=[54321]),
            patch.object(control_panel.os, "kill") as kill,
            patch.object(control_panel.time, "sleep"),
        ):
            result = self.controller.stop()

        self.assertTrue(result.success)
        kill.assert_called_once_with(54321, control_panel.signal.SIGTERM)
        self.assertIn("has stopped", result.message)

    def test_update_runs_deployment_steps_then_starts_server(self):
        self.create_virtualenv_python()
        with (
            patch.object(self.controller, "create_backup", return_value=control_panel.ActionResult(True, "Backed up")),
            patch.object(self.controller, "stop", return_value=control_panel.ActionResult(True, "Stopped")),
            patch.object(self.controller, "start", return_value=control_panel.ActionResult(True, "Started")),
            patch.object(control_panel.subprocess, "run", return_value=Mock(returncode=0, stdout="", stderr="")) as run,
        ):
            result = self.controller.update()

        self.assertTrue(result.success)
        self.assertEqual(run.call_count, 4)
        self.assertEqual(run.call_args_list[0].args[0], ["git", "pull", "--ff-only", "origin", "main"])

    def test_reinstall_fetches_and_restores_the_current_github_version(self):
        self.create_virtualenv_python()
        with (
            patch.object(self.controller, "create_backup", return_value=control_panel.ActionResult(True, "Backed up")),
            patch.object(self.controller, "stop", return_value=control_panel.ActionResult(True, "Stopped")),
            patch.object(self.controller, "start", return_value=control_panel.ActionResult(True, "Started")),
            patch.object(control_panel.subprocess, "run", return_value=Mock(returncode=0, stdout="", stderr="")) as run,
        ):
            result = self.controller.update(reinstall=True)

        self.assertTrue(result.success)
        self.assertEqual(run.call_count, 5)
        self.assertEqual(run.call_args_list[0].args[0], ["git", "fetch", "--quiet", "origin", "main"])
        self.assertEqual(run.call_args_list[1].args[0], ["git", "reset", "--hard", "FETCH_HEAD"])

    def test_update_reports_progress_for_each_deployment_stage(self):
        self.create_virtualenv_python()
        progress = Mock()
        with (
            patch.object(self.controller, "create_backup", return_value=control_panel.ActionResult(True, "Backed up")),
            patch.object(self.controller, "stop", return_value=control_panel.ActionResult(True, "Stopped")),
            patch.object(self.controller, "start", return_value=control_panel.ActionResult(True, "Started")),
            patch.object(control_panel.subprocess, "run", return_value=Mock(returncode=0, stdout="", stderr="")),
        ):
            result = self.controller.update(progress=progress)

        self.assertTrue(result.success)
        self.assertEqual(
            [call.args[0] for call in progress.call_args_list],
            [
                "Creating database backup...",
                "Stopping Welcome System...",
                "Downloading updates from GitHub...",
                "Installing application requirements...",
                "Applying database updates...",
                "Preparing static files...",
                "Starting Welcome System...",
            ],
        )

    def test_open_github_uses_the_default_browser(self):
        with patch.object(control_panel.webbrowser, "open", return_value=True) as open_browser:
            result = self.controller.open_github()

        self.assertTrue(result.success)
        open_browser.assert_called_once_with(control_panel.GITHUB_REPOSITORY_URL, new=2)


class ControlPanelWindowTests(unittest.TestCase):
    def test_button_row_uses_colored_actions_and_native_secondary_buttons(self):
        ttk_buttons = []
        tk_buttons = []

        class FakeWidget:
            def pack(self, **kwargs):
                return kwargs

            def bind(self, *_args):
                return None

            def configure(self, **_kwargs):
                return None

        class FakeTtk:
            @staticmethod
            def Frame(parent):
                return FakeWidget()

            @staticmethod
            def Button(parent, text, command):
                ttk_buttons.append((text, command))
                return FakeWidget()

        class FakeTk:
            @staticmethod
            def Label(parent, **kwargs):
                tk_buttons.append(kwargs)
                return FakeWidget()

        window = control_panel.ControlPanelWindow.__new__(control_panel.ControlPanelWindow)
        window.ttk = FakeTtk
        window.tk = FakeTk
        window._button_row(
            FakeWidget(),
            [("Start", lambda: None, "start"), ("Stop", lambda: None, "stop"), ("Restart", lambda: None)],
        )

        self.assertEqual([button["text"] for button in tk_buttons], ["Start", "Stop"])
        self.assertEqual([button["background"] for button in tk_buttons], ["#198754", "#dc3545"])
        self.assertEqual([text for text, _command in ttk_buttons], ["Restart"])

    def test_status_refresh_does_not_show_an_error_popup(self):
        window = control_panel.ControlPanelWindow.__new__(control_panel.ControlPanelWindow)
        window.controller = Mock()
        window._run = Mock()

        window.refresh_status()

        window._run.assert_called_once_with(window.controller.status, show_error=False)

    def test_open_github_runs_the_controller_action(self):
        window = control_panel.ControlPanelWindow.__new__(control_panel.ControlPanelWindow)
        window.controller = Mock()
        window._run = Mock()

        window.open_github()

        window._run.assert_called_once_with(window.controller.open_github)

    def test_successful_update_refreshes_the_displayed_version(self):
        version_text = Mock()
        window = control_panel.ControlPanelWindow.__new__(control_panel.ControlPanelWindow)
        window.controller = Mock(app_version="0.9.10-beta")
        window.version_text = version_text
        window.refresh_update_status = Mock()

        window._refresh_version_after_update()

        version_text.set.assert_called_once_with("Installed version: 0.9.10-beta")
        window.refresh_update_status.assert_called_once_with()

    def test_update_offers_to_reinstall_when_already_up_to_date(self):
        window = control_panel.ControlPanelWindow.__new__(control_panel.ControlPanelWindow)
        window.controller = Mock()
        window.update_available = False
        window._run = Mock()

        window.update()

        action, confirmation = window._run.call_args.args[:2]
        self.assertIn("already up to date", confirmation)
        action()
        self.assertTrue(window.controller.update.called)
        self.assertTrue(window.controller.update.call_args.kwargs["reinstall"])
        self.assertTrue(callable(window.controller.update.call_args.kwargs["progress"]))


if __name__ == "__main__":
    unittest.main()
