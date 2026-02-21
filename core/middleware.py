from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from jazzmin.settings import THEMES

from .settings_store import get_setting


class AdminSkinMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            selected_skin = "default"
            try:
                raw_skin = (get_setting("admin_skin", "default") or "").strip().lower()
                if raw_skin in THEMES:
                    selected_skin = raw_skin
            except (OperationalError, ProgrammingError):
                selected_skin = "default"

            ui_tweaks = dict(getattr(settings, "JAZZMIN_UI_TWEAKS", {}))
            ui_tweaks["theme"] = selected_skin
            settings.JAZZMIN_UI_TWEAKS = ui_tweaks

        return self.get_response(request)
