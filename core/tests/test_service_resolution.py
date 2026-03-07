from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.models import Service
from core.permissions import ROLE_GREETER


class ServiceResolutionTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name=ROLE_GREETER)
        self.user = User.objects.create_user(username="greeter", password="pw", is_active=True)
        self.user.groups.add(Group.objects.get(name=ROLE_GREETER))
        self.client.force_login(self.user)

    def test_kiosk_status_handles_duplicate_today_services(self):
        today = date.today()
        Service.objects.create(date=today, label="Service A", status=Service.CLOSED)
        Service.objects.create(date=today, label="Service B", status=Service.OPEN)

        response = self.client.get("/kiosk/status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("service_open"))
        self.assertEqual(payload.get("service_label"), "Service B")
