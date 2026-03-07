from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Attendance, Person, Service


class ServiceManualActionsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.admin_user)
        self.service = Service.objects.create(date="2026-02-21", label="Sabbath Service 02-21-2026", status=Service.OPEN)
        self.url = f"/admin/core/service/{self.service.id}/change/"

    def test_manual_checkin_person_creates_attendance_once(self):
        person = Person.objects.create(first_name="Ada", last_name="Lovelace", member_type=Person.MEMBER)

        response1 = self.client.post(
            self.url,
            {"action": "manual_checkin_person", "person_id": person.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        response2 = self.client.post(
            self.url,
            {"action": "manual_checkin_person", "person_id": person.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response1.status_code, 204)
        self.assertEqual(response2.status_code, 204)
        self.assertEqual(Attendance.objects.filter(service=self.service, person=person).count(), 1)

    def test_manual_print_person_returns_print_url(self):
        person = Person.objects.create(first_name="Grace", last_name="Hopper", member_type=Person.MEMBER)

        response = self.client.post(
            self.url,
            {"action": "manual_print_person", "person_id": person.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        attendance = Attendance.objects.get(service=self.service, person=person)
        self.assertEqual(response.json().get("print_url"), f"/print/{attendance.id}/")

    def test_manual_create_visitor_print_creates_visitor_and_attendance(self):
        response = self.client.post(
            self.url,
            {
                "action": "manual_create_visitor_print",
                "first_name": "New",
                "last_name": "Visitor",
                "phone": "5551234567",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        person = Person.objects.get(first_name="New", last_name="Visitor")
        self.assertEqual(person.member_type, Person.VISITOR)
        attendance = Attendance.objects.get(service=self.service, person=person)
        self.assertEqual(response.json().get("print_url"), f"/print/{attendance.id}/")

    def test_manual_actions_blocked_when_service_closed(self):
        person = Person.objects.create(first_name="Jane", last_name="Doe", member_type=Person.MEMBER)
        self.service.status = Service.CLOSED
        self.service.save(update_fields=["status"])

        response = self.client.post(
            self.url,
            {"action": "manual_checkin_person", "person_id": person.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(Attendance.objects.filter(service=self.service, person=person).exists())
