from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.member_import import import_member_rows, parse_member_csv
from core.models import AuditLog, Family, Person


def csv_file(content: str, name: str = "members.csv"):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


class MemberImportParserTests(TestCase):
    def test_parse_member_csv_validates_and_normalizes_rows(self):
        rows = parse_member_csv(
            csv_file(
                "First Name,Middle Initial,Last Name,Family,Phone,Email,Birth Month,Birth Day,Active\n"
                "Jane,q,Example,Example Family,5551234567,jane@example.com,4,16,yes\n"
            )
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row.is_valid)
        self.assertEqual(row.data["middle_initial"], "Q")
        self.assertEqual(row.data["birth_month"], 4)
        self.assertEqual(row.data["birth_day"], 16)
        self.assertTrue(row.data["is_active"])

    def test_parse_member_csv_reports_missing_required_names(self):
        rows = parse_member_csv(csv_file("First Name,Last Name\n,Example\n"))

        self.assertFalse(rows[0].is_valid)
        self.assertIn("First name is required.", rows[0].errors)

    def test_import_member_rows_creates_member_and_family(self):
        rows = parse_member_csv(
            csv_file(
                "First Name,Last Name,Family,Phone,Email\n"
                "Jane,Example,Example Family,5551234567,jane@example.com\n"
            )
        )

        result = import_member_rows(rows)

        self.assertEqual(result.created, 1)
        person = Person.objects.get(email="jane@example.com")
        self.assertEqual(person.member_type, Person.MEMBER)
        self.assertEqual(person.family.name, "Example")

    def test_import_member_rows_skips_existing_by_default(self):
        Person.objects.create(first_name="Jane", last_name="Example", email="jane@example.com", member_type=Person.VISITOR)
        rows = parse_member_csv(csv_file("First Name,Last Name,Email\nJane,Example,jane@example.com\n"))

        result = import_member_rows(rows)

        self.assertEqual(result.skipped, 1)
        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Person.objects.get(email="jane@example.com").member_type, Person.VISITOR)

    def test_import_member_rows_can_update_existing(self):
        Person.objects.create(first_name="Jane", last_name="Example", email="jane@example.com", member_type=Person.VISITOR)
        rows = parse_member_csv(csv_file("First Name,Last Name,Phone,Email\nJane,Example,5551234567,jane@example.com\n"))

        result = import_member_rows(rows, update_existing=True)

        self.assertEqual(result.updated, 1)
        person = Person.objects.get(email="jane@example.com")
        self.assertEqual(person.member_type, Person.MEMBER)
        self.assertEqual(person.phone, "5551234567")


class MemberImportAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.admin_user)

    def test_preview_member_import_does_not_create_people(self):
        response = self.client.post(
            "/admin/member-import/",
            {
                "action": "preview_members",
                "member_file": csv_file("First Name,Last Name,Email\nJane,Example,jane@example.com\n"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview ready")
        self.assertFalse(Person.objects.exists())

    def test_import_member_csv_creates_people_and_logs_action(self):
        response = self.client.post(
            "/admin/member-import/",
            {
                "action": "import_members",
                "member_file": csv_file("First Name,Last Name,Family,Email\nJane,Example,Example Family,jane@example.com\n"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import complete")
        self.assertTrue(Person.objects.filter(email="jane@example.com", member_type=Person.MEMBER).exists())
        self.assertTrue(Family.objects.filter(name="Example").exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_MEMBER_IMPORT).exists())

    def test_sample_csv_download(self):
        response = self.client.get("/admin/member-import/sample/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("First Name", response.content.decode("utf-8"))
