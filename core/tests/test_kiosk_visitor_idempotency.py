from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from unittest.mock import patch

from core.models import Attendance, Person, Service
from core.permissions import ROLE_GREETER


class KioskVisitorIdempotencyTests(TestCase):
    def setUp(self):
        greeter_group, _ = Group.objects.get_or_create(name=ROLE_GREETER)
        self.user = User.objects.create_user(username="greeter", password="pw", is_active=True)
        self.user.groups.add(greeter_group)
        self.client.force_login(self.user)
        self.service = Service.objects.create(
            date=date.today(),
            label="Sabbath Service",
            status=Service.OPEN,
        )

    def test_repeated_visitor_submission_creates_one_person_and_attendance(self):
        payload = {
            "action": "check_in_only",
            "first_name": "Jane",
            "last_name": "Visitor",
            "phone": "555-0100",
            "submission_token": "visitor-submission-token-0001",
        }

        first_response = self.client.post(
            "/kiosk/",
            payload,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        second_response = self.client.post(
            "/kiosk/",
            payload,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(first_response.json()["checked_in"])
        self.assertTrue(second_response.json()["checked_in"])
        self.assertEqual(Person.objects.filter(first_name="Jane", last_name="Visitor").count(), 1)
        person = Person.objects.get(kiosk_submission_token=payload["submission_token"])
        self.assertEqual(Attendance.objects.filter(person=person, service=self.service).count(), 1)

    def test_kiosk_page_includes_submission_token_field(self):
        response = self.client.get("/kiosk/")

        self.assertContains(response, 'name="submission_token"')
        self.assertContains(response, 'id="visitor-submission-token"')


class KioskValidationTests(KioskVisitorIdempotencyTests):
    def post(self, payload):
        return self.client.post("/kiosk/", payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_invalid_visitors_never_create_records(self):
        cases = [
            {"first_name": " "}, {"last_name": ""}, {"email": "invalid"},
            {"birth_month": "99", "birth_day": "1"},
            {"birth_month": "2", "birth_day": "30"},
            {"birth_month": "1"}, {"first_name": "A" * 121},
            {"middle_initial": "ABC"}, {"action": "unknown"},
            {"submission_token": "bad"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.post({"action": "check_in_only", "first_name": "Jane", "last_name": "Visitor", **changes})
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())
                self.assertFalse(Person.objects.exists())
                self.assertFalse(Attendance.objects.exists())

    def test_leap_day_is_valid(self):
        response = self.post({"action": "check_in_only", "first_name": "Jane", "last_name": "Visitor", "birth_month": "2", "birth_day": "29"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Person.objects.get().birth_day, 29)

    def test_empty_selection_does_not_fall_back_to_primary_person(self):
        person = Person.objects.create(first_name="Test", last_name="Member")
        for action in ["check_in_selected", "print_selected"]:
            response = self.post({"action": action, "primary_person_id": person.pk})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(Attendance.objects.exists())

    def test_invalid_group_member_does_not_partially_check_in_family(self):
        person = Person.objects.create(first_name="Test", last_name="Member")
        response = self.post({"action": "check_in_selected", "person_ids": [person.pk, person.pk + 1]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Attendance.objects.exists())

    def test_audit_failure_rolls_back_visitor_and_attendance(self):
        with patch("core.views.log_event", side_effect=RuntimeError("audit failure")):
            with self.assertRaises(RuntimeError):
                self.post({"action": "check_in_only", "first_name": "Jane", "last_name": "Visitor"})
        self.assertFalse(Person.objects.exists())
        self.assertFalse(Attendance.objects.exists())

    def test_expired_session_returns_actionable_json(self):
        self.client.logout()
        response = self.post({"action": "check_in_only", "first_name": "Jane", "last_name": "Visitor"})
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json()["login_required"])

    def test_closed_service_returns_json_without_creating_visitor(self):
        self.service.status = Service.CLOSED
        self.service.save()
        response = self.post({"action": "check_in_only", "first_name": "Jane", "last_name": "Visitor"})
        self.assertEqual(response.status_code, 423)
        self.assertFalse(Person.objects.exists())

    def test_non_ajax_validation_error_is_visible_after_redirect(self):
        response = self.client.post("/kiosk/", {"action": "check_in_selected"}, follow=True)
        self.assertContains(response, "Select at least one person.")
