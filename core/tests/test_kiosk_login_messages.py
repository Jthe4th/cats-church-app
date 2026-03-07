from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.models import Service
from core.permissions import ROLE_GREETER


class KioskLoginMessageTests(TestCase):
    def setUp(self):
        greeter_group, _ = Group.objects.get_or_create(name=ROLE_GREETER)
        self.user = User.objects.create_user(username="ecc_greeter", password="Welcome123!", is_active=True)
        self.user.groups.add(greeter_group)
        Service.objects.create(date=date.today(), label=f"Sabbath Service {date.today():%m-%d-%Y}", status=Service.CLOSED)

    def test_closed_service_shows_closed_message_not_role_error(self):
        response = self.client.post("/kiosk/", {"username": "ecc_greeter", "password": "Welcome123!"})
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Service is closed. Ask staff to reopen it in Admin.", html)
        self.assertNotIn("Access requires a Greeter or Admin role.", html)
