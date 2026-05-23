import base64
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.models import Attendance, AuditLog, Person, Service, SystemSetting
from core.permissions import ROLE_ADMIN, ROLE_GREETER
from core.printnode import (
    PRINT_MODE_PRINTNODE,
    PRINT_MODE_SERVER,
    PrintNodeError,
    ServerPrinterError,
    build_test_label_raw,
    build_test_label_pdf,
    get_kiosk_printer_id,
    get_kiosk_server_printer,
    submit_attendance_print_job,
    submit_server_attendance_print_job,
)


class PrintNodeKioskTests(TestCase):
    def setUp(self):
        greeter_group, _ = Group.objects.get_or_create(name=ROLE_GREETER)
        self.user = User.objects.create_user(username="greeter", password="pw", is_active=True)
        self.user.groups.add(greeter_group)
        self.client.force_login(self.user)
        self.service = Service.objects.create(date=date.today(), label="Sabbath Service", status=Service.OPEN)
        self.person = Person.objects.create(first_name="Ada", last_name="Lovelace", member_type=Person.MEMBER)
        SystemSetting.objects.update_or_create(key="print_mode", defaults={"value": PRINT_MODE_PRINTNODE})
        SystemSetting.objects.update_or_create(key="printnode_api_key", defaults={"value": "test-api-key"})
        SystemSetting.objects.update_or_create(key="printnode_printer_map", defaults={"value": '{"kiosk1": "123456"}'})

    @patch("core.views.submit_attendance_print_job", return_value=98765)
    def test_kiosk_print_selected_submits_printnode_job(self, mock_submit):
        response = self.client.post(
            "/kiosk/",
            {"action": "print_selected", "person_ids": [self.person.id], "kiosk_id": "kiosk1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("printed"))
        self.assertEqual(payload.get("print_mode"), "printnode")
        self.assertNotIn("print_url", payload)
        attendance = Attendance.objects.get(service=self.service, person=self.person)
        mock_submit.assert_called_once_with([attendance.id], kiosk_id="kiosk1", user=self.user)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_PRINTNODE_SUCCESS).exists())

    @patch("core.views.submit_attendance_print_job", side_effect=PrintNodeError("No printer configured."))
    def test_kiosk_printnode_failure_is_visible_and_keeps_attendance(self, mock_submit):
        response = self.client.post(
            "/kiosk/",
            {"action": "print_selected", "person_ids": [self.person.id], "kiosk_id": "kiosk1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("No printer configured.", response.json().get("print_error", ""))
        self.assertTrue(Attendance.objects.filter(service=self.service, person=self.person).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_PRINTNODE_FAILURE).exists())
        self.assertTrue(mock_submit.called)

    def test_printnode_status_reports_ready_for_mapped_kiosk(self):
        response = self.client.get("/kiosk/printnode-status/?kiosk=kiosk1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "ready")
        self.assertEqual(payload.get("label"), "PrintNode: ready")
        self.assertEqual(payload.get("printer_id"), 123456)

    def test_printnode_status_reports_unmapped_printer(self):
        response = self.client.get("/kiosk/printnode-status/?kiosk=kiosk2")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "printer_not_mapped")
        self.assertEqual(payload.get("label"), "PrintNode: printer not mapped")

    @patch("core.views.submit_test_print_job", return_value=24680)
    def test_kiosk_test_print_submits_printnode_job_without_attendance(self, mock_submit):
        response = self.client.post(
            "/kiosk/test-print/",
            {"kiosk_id": "kiosk1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("printed"))
        mock_submit.assert_called_once_with(kiosk_id="kiosk1")
        self.assertEqual(Attendance.objects.count(), 0)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.ACTION_PRINTNODE_SUCCESS,
                metadata__source="kiosk_test_print",
            ).exists()
        )


class PrintNodeSettingsTests(TestCase):
    def test_get_kiosk_printer_id_reads_json_map(self):
        SystemSetting.objects.update_or_create(
            key="printnode_printer_map",
            defaults={"value": '{"kiosk1": "123456", "side-door": 123457}'},
        )

        self.assertEqual(get_kiosk_printer_id("kiosk1"), 123456)
        self.assertEqual(get_kiosk_printer_id("side-door"), 123457)

    def test_get_kiosk_printer_id_rejects_missing_mapping(self):
        SystemSetting.objects.update_or_create(key="printnode_printer_map", defaults={"value": "{}"})

        with self.assertRaises(PrintNodeError):
            get_kiosk_printer_id("kiosk1")

    def test_test_label_pdf_uses_configured_brother_label_size(self):
        SystemSetting.objects.update_or_create(key="printnode_label_width_in", defaults={"value": "2.440"})
        SystemSetting.objects.update_or_create(key="printnode_label_height_in", defaults={"value": "1.1"})

        pdf_text = build_test_label_pdf("kiosk1").decode("utf-8", errors="ignore")

        self.assertIn("/MediaBox [0 0 175.68 79.20]", pdf_text)
        self.assertIn("1.000 0.000 0.000 RG", pdf_text)
        self.assertIn("(TEST)", pdf_text)
        self.assertIn("(KIOSK KIOSK1)", pdf_text)

    def test_test_label_raw_uses_brother_ql_raster_mode(self):
        raw_bytes = build_test_label_raw("kiosk1")

        self.assertIn(b"\x1bia\x01", raw_bytes)
        self.assertIn(b"\x1biK\t", raw_bytes)
        self.assertGreater(len(raw_bytes), 1000)

    @patch("core.printnode.submit_printnode_job", return_value=13579)
    def test_printnode_payload_uses_raw_brother_raster(self, mock_submit):
        service = Service.objects.create(date=date.today(), label="Sabbath Service", status=Service.OPEN)
        person = Person.objects.create(first_name="Ada", last_name="Lovelace", member_type=Person.MEMBER)
        attendance = Attendance.objects.create(service=service, person=person)
        SystemSetting.objects.update_or_create(key="printnode_api_key", defaults={"value": "test-api-key"})
        SystemSetting.objects.update_or_create(key="printnode_printer_map", defaults={"value": '{"kiosk1": "123456"}'})

        print_job_id = submit_attendance_print_job([attendance.id], kiosk_id="kiosk1")

        self.assertEqual(print_job_id, 13579)
        _api_key, payload = mock_submit.call_args.args
        self.assertEqual(payload["contentType"], "raw_base64")
        self.assertNotIn("options", payload)
        decoded = base64.b64decode(payload["content"])
        self.assertIn(b"\x1bia\x01", decoded)
        self.assertIn(b"\x1biK\t", decoded)


class ServerPrinterKioskTests(TestCase):
    def setUp(self):
        greeter_group, _ = Group.objects.get_or_create(name=ROLE_GREETER)
        self.user = User.objects.create_user(username="server-greeter", password="pw", is_active=True)
        self.user.groups.add(greeter_group)
        self.client.force_login(self.user)
        self.service = Service.objects.create(date=date.today(), label="Sabbath Service", status=Service.OPEN)
        self.person = Person.objects.create(first_name="Ada", last_name="Lovelace", member_type=Person.MEMBER)
        SystemSetting.objects.update_or_create(key="print_mode", defaults={"value": PRINT_MODE_SERVER})
        SystemSetting.objects.update_or_create(
            key="server_printer_map",
            defaults={"value": '{"kiosk1": "192.168.1.50:9100"}'},
        )

    @patch("core.views.submit_server_attendance_print_job", return_value="192.168.1.50:9100")
    def test_kiosk_print_selected_submits_server_printer_job(self, mock_submit):
        response = self.client.post(
            "/kiosk/",
            {"action": "print_selected", "person_ids": [self.person.id], "kiosk_id": "kiosk1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("printed"))
        self.assertEqual(payload.get("print_mode"), "server")
        self.assertEqual(payload.get("print_mode_label"), "Server Printer")
        self.assertNotIn("print_url", payload)
        attendance = Attendance.objects.get(service=self.service, person=self.person)
        mock_submit.assert_called_once_with([attendance.id], kiosk_id="kiosk1", user=self.user)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_SERVER_PRINT_SUCCESS).exists())

    @patch("core.views.submit_server_attendance_print_job", side_effect=ServerPrinterError("Printer offline."))
    def test_kiosk_server_printer_failure_is_visible_and_keeps_attendance(self, mock_submit):
        response = self.client.post(
            "/kiosk/",
            {"action": "print_selected", "person_ids": [self.person.id], "kiosk_id": "kiosk1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Printer offline.", response.json().get("print_error", ""))
        self.assertTrue(Attendance.objects.filter(service=self.service, person=self.person).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_SERVER_PRINT_FAILURE).exists())
        self.assertTrue(mock_submit.called)

    def test_server_printer_status_reports_ready_for_mapped_kiosk(self):
        response = self.client.get("/kiosk/printer-status/?kiosk=kiosk1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("status"), "ready")
        self.assertEqual(payload.get("label"), "Server Printer: ready")
        self.assertEqual(payload.get("printer_address"), "192.168.1.50:9100")

    @patch("core.views.submit_server_test_print_job", return_value="192.168.1.50:9100")
    def test_kiosk_test_print_submits_server_printer_job_without_attendance(self, mock_submit):
        response = self.client.post(
            "/kiosk/test-print/",
            {"kiosk_id": "kiosk1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("printed"))
        self.assertEqual(response.json().get("print_mode_label"), "Server Printer")
        mock_submit.assert_called_once_with(kiosk_id="kiosk1")
        self.assertEqual(Attendance.objects.count(), 0)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.ACTION_SERVER_PRINT_SUCCESS,
                metadata__source="kiosk_test_print",
            ).exists()
        )


class ServerPrinterSettingsTests(TestCase):
    def test_get_kiosk_server_printer_reads_json_map(self):
        SystemSetting.objects.update_or_create(
            key="server_printer_map",
            defaults={"value": '{"kiosk1": "192.168.1.50:9100", "side-door": {"host": "printer.local", "port": 9100}}'},
        )

        self.assertEqual(get_kiosk_server_printer("kiosk1"), ("192.168.1.50", 9100))
        self.assertEqual(get_kiosk_server_printer("side-door"), ("printer.local", 9100))

    def test_get_kiosk_server_printer_rejects_missing_mapping(self):
        SystemSetting.objects.update_or_create(key="server_printer_map", defaults={"value": "{}"})

        with self.assertRaises(ServerPrinterError):
            get_kiosk_server_printer("kiosk1")

    @patch("core.printnode._send_raw_to_server_printer")
    def test_server_printer_job_sends_raw_brother_raster_to_configured_address(self, mock_send):
        service = Service.objects.create(date=date.today(), label="Sabbath Service", status=Service.OPEN)
        person = Person.objects.create(first_name="Ada", last_name="Lovelace", member_type=Person.MEMBER)
        attendance = Attendance.objects.create(service=service, person=person)
        SystemSetting.objects.update_or_create(
            key="server_printer_map",
            defaults={"value": '{"kiosk1": "192.168.1.50:9100"}'},
        )

        destination = submit_server_attendance_print_job([attendance.id], kiosk_id="kiosk1")

        self.assertEqual(destination, "192.168.1.50:9100")
        host, port, raw_bytes = mock_send.call_args.args
        self.assertEqual(host, "192.168.1.50")
        self.assertEqual(port, 9100)
        self.assertIn(b"\x1bia\x01", raw_bytes)
        self.assertIn(b"\x1biK\t", raw_bytes)


class PrintNodeFallbackTests(TestCase):
    def test_staff_print_page_remains_available_in_printnode_mode(self):
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(admin_user)
        SystemSetting.objects.update_or_create(key="print_mode", defaults={"value": PRINT_MODE_PRINTNODE})
        service = Service.objects.create(date=date.today(), label="Sabbath Service", status=Service.OPEN)
        person = Person.objects.create(first_name="Grace", last_name="Hopper", member_type=Person.MEMBER)
        attendance = Attendance.objects.create(service=service, person=person)

        response = self.client.get(f"/print/{attendance.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GRACE")

    def test_browser_print_page_uses_configured_label_size(self):
        admin_user = User.objects.create_superuser(
            username="label-admin",
            email="label-admin@example.com",
            password="password123",
        )
        self.client.force_login(admin_user)
        SystemSetting.objects.update_or_create(key="printnode_label_width_in", defaults={"value": "2.440"})
        SystemSetting.objects.update_or_create(key="printnode_label_height_in", defaults={"value": "1.1"})
        SystemSetting.objects.update_or_create(key="printnode_label_margin_in", defaults={"value": "0.1"})
        service = Service.objects.create(date=date.today(), label="Sabbath Service", status=Service.OPEN)
        person = Person.objects.create(first_name="Grace", last_name="Hopper", member_type=Person.MEMBER)
        attendance = Attendance.objects.create(service=service, person=person)

        response = self.client.get(f"/print/{attendance.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "size: 2.440in 1.100in landscape")
        self.assertContains(response, "--label-width: 2.440in")
        self.assertContains(response, "--label-height: 1.100in")
        self.assertContains(response, "--label-margin: 0.100in")


class PrintNodeAdminSettingsTests(TestCase):
    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        self.admin_user = User.objects.create_superuser(
            username="settings-admin",
            email="settings-admin@example.com",
            password="password123",
        )
        self.admin_user.groups.add(admin_group)
        self.client.force_login(self.admin_user)
        SystemSetting.objects.update_or_create(key="printnode_api_key", defaults={"value": "test-api-key"})

    def test_verify_button_shows_when_printnode_mode_selected(self):
        SystemSetting.objects.update_or_create(key="print_mode", defaults={"value": PRINT_MODE_PRINTNODE})

        response = self.client.get("/admin/core/systemsetting/bulk/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verify PrintNode API Key")
        self.assertNotContains(response, 'class="printnode-verify-row" hidden')

    def test_verify_button_hidden_when_connected_printer_mode_selected(self):
        SystemSetting.objects.update_or_create(key="print_mode", defaults={"value": "Connected Printer"})

        response = self.client.get("/admin/core/systemsetting/bulk/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="printnode-verify-row" hidden')

    @patch("core.admin.verify_printnode_api_key", return_value=(True, "PrintNode API key verified."))
    def test_verify_printnode_api_key_endpoint_checks_posted_key(self, mock_verify):
        response = self.client.post(
            "/admin/core/systemsetting/verify-printnode-api-key/",
            {"api_key": "fresh-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "message": "PrintNode API key verified."})
        mock_verify.assert_called_once_with("fresh-key")
