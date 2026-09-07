"""Resolve one automatic service per local calendar day."""
from django.utils import timezone

from .models import Service


def get_current_service():
    today = timezone.localdate()
    same_day = Service.objects.filter(date=today)
    existing = same_day.filter(status=Service.OPEN).order_by("-id").first()
    existing = existing or same_day.order_by("-id").first()
    if existing:
        return existing
    # The unique automatic date makes simultaneous first requests converge.
    # Manual/historical same-day services remain supported.
    service, _ = Service.objects.get_or_create(
        automatic_date=today,
        defaults={"date": today, "label": f"Sabbath Service {today:%m-%d-%Y}"},
    )
    return service
