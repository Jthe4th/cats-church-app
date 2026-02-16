from datetime import date

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .models import Service
from .settings_store import ensure_default_groups, ensure_default_settings


def _service_label(service_date: date) -> str:
    return f"Sabbath Service {service_date.strftime('%m-%d-%Y')}"


@receiver(user_logged_in)
def ensure_sabbath_service(sender, user, request, **kwargs):
    today = date.today()
    if today.weekday() != 5:  # Saturday
        return
    Service.objects.get_or_create(
        date=today,
        label=_service_label(today),
    )


@receiver(post_migrate)
def bootstrap_defaults_after_migrate(sender, app_config=None, **kwargs):
    # Seed defaults only after migrations, to avoid DB access during app startup.
    if app_config and app_config.name != "core":
        return
    ensure_default_settings()
    ensure_default_groups()
