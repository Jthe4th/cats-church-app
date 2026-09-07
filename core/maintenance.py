"""Cross-process request gate for database restoration on Windows and Unix.

An independent SQLite file holds shared locks for normal requests and an
exclusive lock for a restore. OS-managed locks disappear if a process exits.
The coordination file is never part of the restored application database.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import sqlite3

from django.conf import settings
from django.http import HttpResponse, JsonResponse

_exclusive_access = ContextVar("database_exclusive_access", default=False)


class MaintenanceBusy(Exception):
    pass


@contextmanager
def database_access(*, exclusive=False):
    if _exclusive_access.get():
        yield
        return
    path = Path(getattr(settings, "DATABASE_MAINTENANCE_LOCK_PATH", settings.BASE_DIR / "maintenance.sqlite3"))
    connection = sqlite3.connect(path, timeout=5 if exclusive else 0.2)
    token = None
    try:
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS access_gate (id INTEGER PRIMARY KEY)")
            connection.execute("BEGIN EXCLUSIVE" if exclusive else "BEGIN")
            connection.execute("SELECT * FROM access_gate").fetchall()
        except sqlite3.OperationalError as exc:
            raise MaintenanceBusy("The database is busy. Wait a moment and try again.") from exc
        token = _exclusive_access.set(exclusive)
        yield
    finally:
        if token is not None:
            _exclusive_access.reset(token)
        connection.close()


class DatabaseMaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Acquire before session/auth reads, and hold through session saving.
        # The view still enforces authentication, authorization and confirmation.
        restoring = (
            request.path == "/admin/database-backup/"
            and request.method == "POST"
            and request.POST.get("action") == "restore_backup"
        )
        try:
            with database_access(exclusive=restoring):
                return self.get_response(request)
        except MaintenanceBusy:
            message = "Database maintenance is in progress. Please wait and try again."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                response = JsonResponse({"error": message}, status=503)
            else:
                response = HttpResponse(message, status=503, content_type="text/plain")
            response["Retry-After"] = "5"
            return response
