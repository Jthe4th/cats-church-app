from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase

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
