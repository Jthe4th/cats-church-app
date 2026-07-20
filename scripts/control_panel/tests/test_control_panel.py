import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


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


if __name__ == "__main__":
    unittest.main()
