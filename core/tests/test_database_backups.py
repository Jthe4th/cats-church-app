from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from django.contrib.sessions.models import Session

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings

from core.backups import create_database_backup, list_database_backups, restore_database_backup, validate_sqlite_database, BackupError
from core.models import AuditLog, Person


class DatabaseBackupAdminTests(TransactionTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.override = override_settings(DATABASE_BACKUP_DIR=Path(self.temp_dir.name))
        self.override.enable()
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.client.force_login(self.admin_user)

    def tearDown(self):
        self.override.disable()
        self.temp_dir.cleanup()

    def test_backup_page_creates_timestamped_database_backup(self):
        response = self.client.post("/admin/database-backup/", {"action": "create_backup"})

        self.assertEqual(response.status_code, 302)
        backups = list_database_backups()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].name.startswith("welcome-system-manual-"))
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_DATABASE_BACKUP).exists())

    def test_backup_download_returns_sqlite_file(self):
        backup = create_database_backup()

        response = self.client.get(f"/admin/database-backup/download/{backup.name}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.sqlite3")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_restore_requires_explicit_confirmation(self):
        backup = create_database_backup()
        Person.objects.create(first_name="After", last_name="Backup")

        response = self.client.post(
            "/admin/database-backup/",
            {
                "action": "restore_backup",
                "backup_name": backup.name,
                "confirm_restore": "on",
                "confirmation_text": "not restore",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Person.objects.filter(first_name="After", last_name="Backup").exists())

    def test_restore_replaces_database_and_requires_new_login(self):
        Person.objects.create(first_name="Before", last_name="Backup")
        backup = create_database_backup()
        Person.objects.create(first_name="After", last_name="Backup")
        response = self.client.post("/admin/database-backup/", {
            "action": "restore_backup", "backup_name": backup.name,
            "confirm_restore": "on", "confirmation_text": "RESTORE",
        })
        self.assertRedirects(response, "/admin/login/", fetch_redirect_response=False)
        self.assertTrue(Person.objects.filter(first_name="Before").exists())
        self.assertFalse(Person.objects.filter(first_name="After").exists())
        self.assertFalse(Session.objects.exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.ACTION_DATABASE_RESTORE).exists())
        self.assertTrue(any(backup.name.startswith("welcome-system-pre-restore-") for backup in list_database_backups()))

    def test_unrelated_database_is_rejected_without_changing_live_data(self):
        path = Path(self.temp_dir.name) / "unrelated.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE unrelated (name TEXT)")
        with self.assertRaises(BackupError):
            restore_database_backup(path.name)
        self.assertTrue(User.objects.filter(pk=self.admin_user.pk).exists())

    def test_old_migration_or_missing_table_is_rejected(self):
        for corruption in ["DELETE FROM django_migrations WHERE app='core'", "DROP TABLE core_person"]:
            backup = create_database_backup()
            with sqlite3.connect(backup.path) as db:
                db.execute(corruption)
            with self.assertRaises(BackupError):
                validate_sqlite_database(backup.path)

    def test_backups_created_at_same_time_have_different_names(self):
        first = create_database_backup()
        second = create_database_backup()
        self.assertNotEqual(first.name, second.name)

    def test_upload_rejects_non_sqlite_file(self):
        uploaded = SimpleUploadedFile("not-a-database.sqlite3", b"this is not sqlite")

        response = self.client.post(
            "/admin/database-backup/",
            {"action": "upload_backup", "backup_file": uploaded},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list_database_backups(), [])
