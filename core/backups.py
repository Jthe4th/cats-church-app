from dataclasses import dataclass
from pathlib import Path
import sqlite3
from uuid import uuid4
from tempfile import TemporaryDirectory

from django.conf import settings
from django.apps import apps
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.utils import timezone
from .maintenance import database_access, MaintenanceBusy


BACKUP_SUFFIX = ".sqlite3"


class BackupError(Exception):
    """Raised when a database backup or restore cannot be completed."""


@dataclass(frozen=True)
class DatabaseBackup:
    name: str
    path: Path
    size_bytes: int
    created_at: object


def get_database_path() -> Path:
    database_name = get_database_name()
    if _is_sqlite_uri(database_name):
        raise BackupError("Database file path is not available for SQLite URI databases.")
    return Path(database_name)


def get_database_name() -> str:
    database = settings.DATABASES["default"]
    if database.get("ENGINE") != "django.db.backends.sqlite3":
        raise BackupError("Database backup is only available for SQLite.")
    return str(database["NAME"])


def get_backup_dir() -> Path:
    backup_dir = Path(getattr(settings, "DATABASE_BACKUP_DIR", settings.BASE_DIR / "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def create_database_backup(*, label: str = "manual") -> DatabaseBackup:
    source_name = get_database_name()
    if not _is_sqlite_uri(source_name) and not Path(source_name).exists():
        raise BackupError(f"Database file not found: {source_name}")

    timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(char for char in label.lower() if char.isalnum() or char in {"-", "_"}).strip("-_")
    safe_label = safe_label or "manual"
    backup_path = get_backup_dir() / f"welcome-system-{safe_label}-{timestamp}-{uuid4().hex[:8]}{BACKUP_SUFFIX}"

    connections.close_all()
    source = sqlite3.connect(source_name, uri=_is_sqlite_uri(source_name))
    try:
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    validate_sqlite_database(backup_path, require_compatible=False)
    return _backup_from_path(backup_path)


def list_database_backups() -> list[DatabaseBackup]:
    backup_dir = get_backup_dir()
    backups = [
        _backup_from_path(path)
        for path in backup_dir.glob(f"*{BACKUP_SUFFIX}")
        if path.is_file() and _is_safe_backup_name(path.name)
    ]
    return sorted(backups, key=lambda backup: backup.created_at, reverse=True)


def get_backup_path(name: str) -> Path:
    if not _is_safe_backup_name(name):
        raise BackupError("Invalid backup file name.")
    path = get_backup_dir() / name
    if not path.exists() or not path.is_file():
        raise BackupError("Backup file not found.")
    return path


def save_uploaded_backup(uploaded_file) -> DatabaseBackup:
    timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    candidate_path = get_backup_dir() / f"welcome-system-uploaded-{timestamp}-{uuid4().hex[:8]}{BACKUP_SUFFIX}"
    with candidate_path.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
    try:
        validate_sqlite_database(candidate_path)
    except BackupError:
        candidate_path.unlink(missing_ok=True)
        raise
    return _backup_from_path(candidate_path)


def restore_database_backup(backup_name: str) -> DatabaseBackup:
    try:
        with database_access(exclusive=True):
            return _restore_database_backup(backup_name)
    except (MaintenanceBusy, sqlite3.DatabaseError, OSError) as exc:
        raise BackupError(f"Restore could not be completed: {exc}") from exc


def _restore_database_backup(backup_name: str) -> DatabaseBackup:
    backup_path = get_backup_path(backup_name)
    # Stage the exact snapshot being restored and remove old sessions before
    # replacement, so even a process exit cannot revive backed-up sessions.
    with TemporaryDirectory(prefix=".restore-", dir=get_backup_dir()) as directory:
        staged_path = Path(directory) / "staged.sqlite3"
        source = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        staged = sqlite3.connect(staged_path)
        try:
            source.backup(staged)
            validate_sqlite_database(staged_path)
            staged.execute("DELETE FROM django_session")
            staged.commit()
            create_database_backup(label="pre-restore")
            database_name = get_database_name()
            connections.close_all()
            destination = sqlite3.connect(database_name, uri=_is_sqlite_uri(database_name))
            try:
                staged.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
            staged.close()
            connections.close_all()
    return _backup_from_path(backup_path)


def validate_sqlite_database(path: Path, *, require_compatible=True) -> None:
    if not path.exists() or not path.is_file():
        raise BackupError("Backup file not found.")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if require_compatible:
                _validate_application_schema(connection)
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError("The selected file is not a valid SQLite database.") from exc
    if not result or result[0] != "ok":
        raise BackupError("SQLite integrity check failed for the selected backup.")


def _validate_application_schema(connection):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "django_migrations" not in tables:
        raise BackupError("This is not a Welcome System backup.")
    applied = set(connection.execute("SELECT app, name FROM django_migrations"))
    expected = set(MigrationLoader(None).disk_migrations)
    if applied != expected:
        raise BackupError("This backup uses a different database version. Restore it with its matching Welcome System version, then update the application.")
    for model in apps.get_models(include_auto_created=True):
        if not model._meta.managed or model._meta.proxy:
            continue
        table = model._meta.db_table
        if table not in tables:
            raise BackupError("The backup is missing required Welcome System tables.")
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not {field.column for field in model._meta.local_fields}.issubset(columns):
            raise BackupError("The backup is missing required Welcome System fields.")
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise BackupError("The backup contains broken record relationships.")


def _backup_from_path(path: Path) -> DatabaseBackup:
    stat = path.stat()
    return DatabaseBackup(
        name=path.name,
        path=path,
        size_bytes=stat.st_size,
        created_at=timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
    )


def _is_safe_backup_name(name: str) -> bool:
    return (
        bool(name)
        and "/" not in name
        and "\\" not in name
        and name.endswith(BACKUP_SUFFIX)
        and all(char.isalnum() or char in {"-", "_", "."} for char in name)
    )


def _is_sqlite_uri(database_name: str) -> bool:
    return database_name.startswith("file:")
