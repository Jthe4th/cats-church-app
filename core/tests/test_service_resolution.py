from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase

from core.models import Service
from core.permissions import ROLE_GREETER


class ServiceResolutionTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name=ROLE_GREETER)
        self.user = User.objects.create_user(username="greeter", password="pw", is_active=True)
        self.user.groups.add(Group.objects.get(name=ROLE_GREETER))
        self.client.force_login(self.user)

    def test_kiosk_status_handles_duplicate_today_services(self):
        today = date.today()
        Service.objects.create(date=today, label="Service A", status=Service.CLOSED)
        Service.objects.create(date=today, label="Service B", status=Service.OPEN)

        response = self.client.get("/kiosk/status/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("service_open"))
        self.assertEqual(payload.get("service_label"), "Service B")

    def test_local_calendar_day_is_used(self):
        from datetime import datetime, timezone as dt_timezone
        from unittest.mock import patch
        from core.services import get_current_service
        with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 8, 1, tzinfo=dt_timezone.utc)):
            service = get_current_service()
        self.assertEqual(service.date.isoformat(), "2026-09-07")

    def test_closed_service_is_not_replaced_or_reopened(self):
        from django.utils import timezone
        from core.services import get_current_service
        service = Service.objects.create(date=timezone.localdate(), status=Service.CLOSED)
        self.assertEqual(get_current_service().pk, service.pk)
        self.assertEqual(Service.objects.count(), 1)

    def test_simultaneous_first_requests_share_automatic_service(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from django.conf import settings
        # Use a disposable file database: shared in-memory SQLite has different
        # locking behavior and cannot reproduce a multi-kiosk installation.
        script = '''
import os, sys, threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
os.environ['DJANGO_SETTINGS_MODULE'] = 'cats.settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0)
from django.db import connections
from django.db.models import QuerySet
from core.models import Service
from core.services import get_current_service
barrier = threading.Barrier(3)
local = threading.local()
original = QuerySet.first
def synchronized_first(queryset):
    result = original(queryset)
    if queryset.model is Service:
        local.reads = getattr(local, 'reads', 0) + 1
        if local.reads == 2:
            barrier.wait(timeout=5)
    return result
def checkin():
    try:
        return get_current_service().pk
    finally:
        connections.close_all()
with patch.object(QuerySet, 'first', synchronized_first):
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(pool.map(lambda _: checkin(), range(3)))
assert len(set(ids)) == 1, ids
assert Service.objects.count() == 1
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-c", script, str(Path(directory) / "race.sqlite3")],
                                    cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_moving_automatic_service_releases_its_original_day(self):
        from datetime import timedelta
        from core.services import get_current_service
        first = get_current_service()
        first.date += timedelta(days=1)
        first.save(update_fields=["date"])
        current = get_current_service()
        self.assertNotEqual(first.pk, current.pk)
        first.refresh_from_db()
        self.assertIsNone(first.automatic_date)
