from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from django.test import SimpleTestCase, RequestFactory, override_settings
from django.http import HttpResponse

from core.maintenance import database_access, DatabaseMaintenanceMiddleware


class MaintenanceTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(DATABASE_MAINTENANCE_LOCK_PATH=Path(self.directory.name) / "gate.sqlite3")
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_restore_waits_for_existing_request_then_blocks_new_requests(self):
        started, acquired, release = Event(), Event(), Event()

        def restore():
            started.set()
            with database_access(exclusive=True):
                acquired.set()
                release.wait(5)

        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                with database_access():
                    future = pool.submit(restore)
                    self.assertTrue(started.wait(2))
                    self.assertFalse(acquired.wait(0.1))
                self.assertTrue(acquired.wait(3))
                middleware = DatabaseMaintenanceMiddleware(lambda request: HttpResponse("should not run"))
                response = middleware(RequestFactory().get("/kiosk/", HTTP_X_REQUESTED_WITH="XMLHttpRequest"))
                self.assertEqual(response.status_code, 503)
                self.assertIn(b"maintenance", response.content)
            finally:
                release.set()
            future.result(timeout=3)
        with database_access():
            pass  # The gate is usable again after restore.

    def test_regular_requests_can_overlap(self):
        with database_access():
            with ThreadPoolExecutor(max_workers=1) as pool:
                def other_request():
                    with database_access():
                        return True
                self.assertTrue(pool.submit(other_request).result(timeout=2))

    def test_exception_releases_exclusive_gate(self):
        with self.assertRaises(ValueError):
            with database_access(exclusive=True):
                raise ValueError("restore failed")
        with database_access(exclusive=True):
            pass
