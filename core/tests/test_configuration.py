import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth.models import Group, User
from cats.configuration import load_environment, env_bool


class ConfigurationTests(SimpleTestCase):
    def test_first_start_generates_persistent_private_configuration(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            first = load_environment(directory)
            second = load_environment(directory)
            self.assertGreaterEqual(len(first["DJANGO_SECRET_KEY"]), 50)
            self.assertEqual(first["DJANGO_SECRET_KEY"], second["DJANGO_SECRET_KEY"])
            self.assertFalse(env_bool(first, "DJANGO_DEBUG"))
            self.assertNotIn("*", first["DJANGO_ALLOWED_HOSTS"])
            if os.name != "nt":
                self.assertEqual((Path(directory) / ".env").stat().st_mode & 0o777, 0o600)

    def test_environment_overrides_file(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / ".env").write_text('DJANGO_DEBUG=False\nDJANGO_ALLOWED_HOSTS="localhost,10.0.0.5"\n')
            with patch.dict(os.environ, {"DJANGO_DEBUG": "True"}, clear=True):
                values = load_environment(directory)
            self.assertTrue(env_bool(values, "DJANGO_DEBUG"))
            self.assertEqual(values["DJANGO_ALLOWED_HOSTS"], "localhost,10.0.0.5")


class ProductionMediaTests(TestCase):
    def test_images_work_without_debug_and_profiles_require_login(self):
        with TemporaryDirectory() as directory, override_settings(DEBUG=False, MEDIA_ROOT=directory):
            root = Path(directory)
            (root / "people/photos").mkdir(parents=True)
            (root / "branding").mkdir()
            (root / "people/photos/test.png").write_bytes(b"test")
            (root / "branding/logo.png").write_bytes(b"logo")
            response = self.client.get("/media/branding/logo.png")
            self.assertEqual(response.status_code, 200)
            response.close()
            self.assertEqual(self.client.get("/media/people/photos/test.png").status_code, 403)
            user = User.objects.create_user(username="greeter")
            user.groups.add(Group.objects.get_or_create(name="Greeter")[0])
            self.client.force_login(user)
            response = self.client.get("/media/people/photos/test.png")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"test")
            response.close()
            self.assertEqual(self.client.get("/media/../cats/settings.py").status_code, 404)
