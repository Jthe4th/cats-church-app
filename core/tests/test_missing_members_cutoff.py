from datetime import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Person, Service


class MissingMembersCutoffTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.admin_user)
        self.service = Service.objects.create(
            date="2026-01-01",
            label="Sabbath Service 01-01-2026",
            status=Service.CLOSED,
        )

    def _set_created_at(self, person: Person, value):
        Person.objects.filter(id=person.id).update(created_at=value)

    def test_missing_members_report_excludes_members_added_after_service_date(self):
        before = Person.objects.create(first_name="Before", last_name="Member", member_type=Person.MEMBER, is_active=True)
        after = Person.objects.create(first_name="After", last_name="Member", member_type=Person.MEMBER, is_active=True)
        unknown = Person.objects.create(first_name="Unknown", last_name="Member", member_type=Person.MEMBER, is_active=True)

        self._set_created_at(before, timezone.make_aware(datetime(2025, 12, 15, 9, 0, 0)))
        self._set_created_at(after, timezone.make_aware(datetime(2026, 1, 15, 9, 0, 0)))
        self._set_created_at(unknown, None)

        response = self.client.get("/admin/missing-members/")
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Before", html)
        self.assertIn("Unknown", html)
        self.assertNotIn("After", html)

    def test_manage_service_live_counts_uses_service_date_cutoff(self):
        before = Person.objects.create(first_name="Before", last_name="Count", member_type=Person.MEMBER, is_active=True)
        after = Person.objects.create(first_name="After", last_name="Count", member_type=Person.MEMBER, is_active=True)

        self._set_created_at(before, timezone.make_aware(datetime(2025, 12, 20, 9, 0, 0)))
        self._set_created_at(after, timezone.make_aware(datetime(2026, 1, 10, 9, 0, 0)))

        response = self.client.get(
            f"/admin/core/service/{self.service.id}/change/?live_counts=1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("missing_member_count"), 1)
