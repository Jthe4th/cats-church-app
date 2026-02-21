from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings

from core.middleware import AdminSkinMiddleware
from core.models import SystemSetting


@override_settings(JAZZMIN_UI_TWEAKS={"theme": "default", "dark_mode_theme": "darkly"})
class AdminSkinMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = AdminSkinMiddleware(lambda request: None)

    def test_applies_saved_skin_for_admin_requests(self):
        SystemSetting.objects.update_or_create(key="admin_skin", defaults={"value": "minty"})
        request = self.factory.get("/admin/")

        self.middleware(request)

        self.assertEqual(settings.JAZZMIN_UI_TWEAKS.get("theme"), "minty")

    def test_falls_back_to_default_for_invalid_skin(self):
        SystemSetting.objects.update_or_create(key="admin_skin", defaults={"value": "not-a-theme"})
        request = self.factory.get("/admin/")

        self.middleware(request)

        self.assertEqual(settings.JAZZMIN_UI_TWEAKS.get("theme"), "default")

    def test_ignores_non_admin_requests(self):
        SystemSetting.objects.update_or_create(key="admin_skin", defaults={"value": "minty"})
        request = self.factory.get("/kiosk/")

        self.middleware(request)

        self.assertEqual(settings.JAZZMIN_UI_TWEAKS.get("theme"), "default")
