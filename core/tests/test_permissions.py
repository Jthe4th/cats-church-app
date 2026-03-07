from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.permissions import (
    ROLE_ADMIN,
    ROLE_GREETER,
    ROLE_PASTOR,
    can_access_admin_site,
    can_access_kiosk,
    can_access_staff_views,
    can_manage_configuration,
    can_print_labels,
    can_view_confidential_notes,
)


class PermissionRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for group_name in (ROLE_GREETER, ROLE_ADMIN, ROLE_PASTOR):
            Group.objects.get_or_create(name=group_name)

    def _make_user(self, username: str, *, is_staff: bool = False, is_active: bool = True, is_superuser: bool = False):
        user = User.objects.create_user(
            username=username,
            password="x",
            is_staff=is_staff,
            is_active=is_active,
            is_superuser=is_superuser,
        )
        return user

    def _assign(self, user: User, *group_names: str):
        for group_name in group_names:
            user.groups.add(Group.objects.get(name=group_name))

    def test_greeter_can_access_kiosk_but_not_admin_or_staff_views(self):
        greeter = self._make_user("greeter")
        self._assign(greeter, ROLE_GREETER)

        self.assertTrue(can_access_kiosk(greeter))
        self.assertFalse(can_access_staff_views(greeter))
        self.assertFalse(can_access_admin_site(greeter))
        self.assertFalse(can_manage_configuration(greeter))
        self.assertFalse(can_view_confidential_notes(greeter))
        self.assertTrue(can_print_labels(greeter))

    def test_admin_staff_can_access_admin_and_manage_configuration(self):
        admin_user = self._make_user("admin", is_staff=True)
        self._assign(admin_user, ROLE_ADMIN)

        self.assertTrue(can_access_kiosk(admin_user))
        self.assertTrue(can_access_staff_views(admin_user))
        self.assertTrue(can_access_admin_site(admin_user))
        self.assertTrue(can_manage_configuration(admin_user))
        self.assertFalse(can_view_confidential_notes(admin_user))
        self.assertTrue(can_print_labels(admin_user))

    def test_pastor_staff_can_access_staff_views_and_confidential_notes_but_not_kiosk_or_config(self):
        pastor = self._make_user("pastor", is_staff=True)
        self._assign(pastor, ROLE_PASTOR)

        self.assertFalse(can_access_kiosk(pastor))
        self.assertTrue(can_access_staff_views(pastor))
        self.assertTrue(can_access_admin_site(pastor))
        self.assertFalse(can_manage_configuration(pastor))
        self.assertTrue(can_view_confidential_notes(pastor))
        self.assertTrue(can_print_labels(pastor))

    def test_inactive_user_is_denied_everywhere(self):
        inactive_admin = self._make_user("inactive-admin", is_staff=True, is_active=False)
        self._assign(inactive_admin, ROLE_ADMIN, ROLE_GREETER, ROLE_PASTOR)

        self.assertFalse(can_access_kiosk(inactive_admin))
        self.assertFalse(can_access_staff_views(inactive_admin))
        self.assertFalse(can_access_admin_site(inactive_admin))
        self.assertFalse(can_manage_configuration(inactive_admin))
        self.assertFalse(can_view_confidential_notes(inactive_admin))
        self.assertFalse(can_print_labels(inactive_admin))

    def test_kiosk_access_allows_case_variants_of_group_name(self):
        Group.objects.get_or_create(name="greeter")
        user = self._make_user("lowercase-greeter")
        user.groups.add(Group.objects.get(name="greeter"))

        self.assertTrue(can_access_kiosk(user))
