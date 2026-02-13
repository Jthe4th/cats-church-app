from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Church Community"

    def ready(self) -> None:
        from . import signals  # noqa: F401
        from .settings_store import ensure_default_groups, ensure_default_settings

        ensure_default_settings()
        ensure_default_groups()
