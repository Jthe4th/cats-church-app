from django.db.utils import OperationalError, ProgrammingError

from .models import SystemSetting


DEFAULT_SETTINGS = {
    "first_name_color": "#000000",
    "last_name_color": "#000000",
    "hide_last_name": "No",
    "label_font": "Arial",
    "kiosk_print_mode": "No",
    "kiosk_print_iframe": "No",
}


def ensure_default_settings() -> None:
    try:
        for key, value in DEFAULT_SETTINGS.items():
            SystemSetting.objects.get_or_create(key=key, defaults={"value": value})
    except (OperationalError, ProgrammingError):
        # Database isn't ready yet (e.g., during migrations).
        return


def get_setting(key: str, default: str = "") -> str:
    setting = SystemSetting.objects.filter(key=key).first()
    if setting and setting.value is not None:
        return setting.value
    return DEFAULT_SETTINGS.get(key, default)
