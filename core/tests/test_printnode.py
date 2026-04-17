from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.models import Attendance, AuditLog, Person, Service, SystemSetting
from core.permissions import ROLE_GREETER
from core.printnode import PRINT_MODE_PRINTNODE, PrintNodeError, get_kiosk_printer_id


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
