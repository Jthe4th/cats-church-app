from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone

from .settings_store import ensure_default_groups, ensure_default_settings
from .services import get_current_service


@receiver(user_logged_in)
def ensure_sabbath_service(sender, user, request, **kwargs):
    today = timezone.localdate()
    if today.weekday() != 5:  # Saturday
        return
    get_current_service()


@receiver(post_migrate)
def bootstrap_defaults_after_migrate(sender, app_config=None, **kwargs):
    # Seed defaults only after migrations, to avoid DB access during app startup.
    if app_config and app_config.name != "core":
        return
    ensure_default_settings()
    ensure_default_groups()
