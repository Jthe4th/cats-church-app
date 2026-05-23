from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.models import Attendance, Person, Service
from core.permissions import ROLE_ADMIN


class AdminDashboardTests(TestCase):
    def setUp(self):
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        self.user = User.objects.create_superuser(
            username="dashboard-admin",
            email="dashboard-admin@example.com",
            password="password123",
        )
        self.user.groups.add(admin_group)
        self.client.force_login(self.user)

    def test_trend_points_are_most_recent_first(self):
        person = Person.objects.create(first_name="Ada", last_name="Lovelace", member_type=Person.MEMBER)
        older = Service.objects.create(date=date(2026, 4, 20), label="Older Service", status=Service.CLOSED)
        newer = Service.objects.create(date=date(2026, 5, 9), label="Newer Service", status=Service.OPEN)
        Attendance.objects.create(service=older, person=person)
        Attendance.objects.create(service=newer, person=person)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        labels = [point["label"] for point in response.context["trend_points"]]
        self.assertLess(labels.index("05/09"), labels.index("04/20"))
