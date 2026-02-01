from datetime import date

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Service


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
