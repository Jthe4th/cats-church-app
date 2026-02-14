"""ASGI config for Welcome System."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cats.settings")

application = get_asgi_application()
