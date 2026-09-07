"""Small, installation-local environment configuration (no shell evaluation)."""
import os
from pathlib import Path
import secrets
import socket
import tempfile

from django.core.exceptions import ImproperlyConfigured


def load_environment(base_dir):
    path = Path(base_dir) / ".env"
    if not path.exists() and not os.environ.get("DJANGO_SECRET_KEY"):
        hosts = ["localhost", "127.0.0.1", "[::1]", socket.gethostname()]
        try:
            hosts.extend(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
        content = (
            f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n"
            "DJANGO_DEBUG=False\n"
            f"DJANGO_ALLOWED_HOSTS={','.join(dict.fromkeys(hosts))}\n"
        )
        # Publish a complete file atomically, including when workers start together.
        fd, temporary = tempfile.mkstemp(prefix=".env-", dir=base_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator:
                raise ImproperlyConfigured("Each .env setting must use KEY=value.")
            value = value.strip()
            if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
                value = value[1:-1]
            values[key.strip()] = value
    return {**values, **os.environ}


def env_bool(values, key, default=False):
    value = str(values.get(key, default)).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ImproperlyConfigured(f"{key} must be True or False.")
    return value in {"true", "1", "yes"}
