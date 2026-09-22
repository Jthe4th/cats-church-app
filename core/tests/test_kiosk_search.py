from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone

from core.models import Family, Person, Service
from core.permissions import ROLE_GREETER


class KioskSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="search-greeter")
        self.user.groups.add(Group.objects.get_or_create(name=ROLE_GREETER)[0])
        self.client.force_login(self.user)
        self.service = Service.objects.create(date=timezone.localdate(), status=Service.OPEN)

    def search(self, query):
        return self.client.get("/kiosk/search-groups/", {"q": query})

    def ids(self, query):
        response = self.search(query)
        self.assertEqual(response.status_code, 200)
        return [m["id"] for g in response.json()["groups"] for m in g["members"]]

    def test_short_names_and_whitespace(self):
        for surname in ("Li", "Ng", "O"):
            person = Person.objects.create(first_name="Test", last_name=surname)
            self.assertIn(person.id, self.ids(" " + surname + " "))
        self.assertEqual(self.ids(" "), [])

    def test_phone_matches_final_normalized_digits_only(self):
        match = Person.objects.create(first_name="Test", last_name="Phone", phone="(555) 123-45-67 ")
        Person.objects.create(first_name="Test", last_name="Middle", phone="4567-555-1234")
        Person.objects.create(first_name="Test", last_name="4567", phone="555-1111")
        self.assertEqual(self.ids("4567"), [match.id])
        for query in ("1", "123", "12345"):
            self.assertEqual(self.search(query).status_code, 400)

    def test_inactive_matches_and_family_members_are_excluded(self):
        family = Family.objects.create(name="Household")
        active = Person.objects.create(first_name="A", last_name="Li", family=family)
        sibling = Person.objects.create(first_name="B", last_name="Ng", family=family)
        Person.objects.create(first_name="C", last_name="Inactive", family=family, is_active=False)
        Person.objects.create(first_name="D", last_name="Li", is_active=False)
        self.assertCountEqual(self.ids("Li"), [active.id, sibling.id])
        self.assertEqual(self.ids("Inactive"), [])

    def test_checked_in_status_is_preserved(self):
        from core.models import Attendance
        person = Person.objects.create(first_name="A", last_name="Li")
        Attendance.objects.create(person=person, service=self.service)
        self.assertTrue(self.search("Li").json()["groups"][0]["members"][0]["checked_in"])

    def test_authentication_and_permissions_return_explicit_errors(self):
        self.client.logout()
        response = self.search("Li")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json()["login_required"])
        self.user.groups.clear()
        self.client.force_login(self.user)
        response = self.search("Li")
        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.json())

    def test_closed_service_blocks_search(self):
        self.service.status = Service.CLOSED
        self.service.save()
        response = self.search("Li")
        self.assertEqual(response.status_code, 423)
        self.assertTrue(response.json()["service_closed"])

    def test_kiosk_assets_are_local_on_login_and_checkin(self):
        for authenticated in (True, False):
            if not authenticated:
                self.client.logout()
            response = self.client.get("/kiosk/")
            self.assertContains(response, "/static/vendor/bootstrap/bootstrap.min.css")
            self.assertNotContains(response, "cdn.jsdelivr.net")
            if authenticated:
                self.assertContains(response, "/static/vendor/bootstrap/bootstrap.bundle.min.js")
