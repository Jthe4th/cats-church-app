from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.models import Group

from .models import SystemSetting


DEFAULT_SETTINGS = {
    "welcome_heading": "Welcome",
    "enable_google_fonts": "Yes",
    "welcome_heading_font": "Arial",
    "welcome_heading_font_source": "system",
    "first_name_color": "#000000",
    "last_name_color": "#000000",
    "kiosk_background_color": "#ffffff",
    "kiosk_background_color_darkmode": "#000000",
    "kiosk_logo_path": "/static/img/EC-SDA-Church_Stacked_Final.png",
    "kiosk_logo_width_px": "200",
    "kiosk_logo_height_px": "",
    "hide_last_name": "No",
    "label_font": "Arial",
    "label_font_source": "system",
    "label_first_name_scale": "100",
    "label_last_name_scale": "100",
    "kiosk_print_mode": "No",
    "kiosk_print_iframe": "No",
    "admin_skin": "default",
}

DEFAULT_SETTING_DESCRIPTIONS = {
    "welcome_heading": "Main heading text shown on the kiosk welcome screen.",
    "enable_google_fonts": "Allow Google Fonts to be used when a font source is set to Google.",
    "welcome_heading_font": "Font family used for the kiosk welcome heading.",
    "welcome_heading_font_source": "Choose whether the welcome heading font comes from system fonts or Google Fonts.",
    "first_name_color": "Text color used for first names on printed nametags.",
    "last_name_color": "Text color used for last names on printed nametags.",
    "kiosk_background_color": "Background color used for the kiosk in light mode.",
    "kiosk_background_color_darkmode": "Background color used for the kiosk in dark mode.",
    "kiosk_logo_path": "Logo image shown on kiosk screens.",
    "kiosk_logo_width_px": "Logo width in pixels for kiosk screens.",
    "kiosk_logo_height_px": "Logo height in pixels for kiosk screens. Leave blank for auto height.",
    "hide_last_name": "Hide last names on printed nametags when set to Yes.",
    "label_font": "Font family used for printed nametags.",
    "label_font_source": "Choose whether the nametag font comes from system fonts or Google Fonts.",
    "label_first_name_scale": "Scale first-name text size on labels as a percentage (100 = default).",
    "label_last_name_scale": "Scale last-name text size on labels as a percentage (100 = default).",
    "kiosk_print_mode": "Automatically open print flow on check-in when set to Yes.",
    "kiosk_print_iframe": "Use in-page iframe print mode instead of navigating away when set to Yes.",
    "admin_skin": "Jazzmin/Bootswatch skin used in the admin area.",
}


def ensure_default_settings() -> None:
    try:
        for key, value in DEFAULT_SETTINGS.items():
            setting, _created = SystemSetting.objects.get_or_create(key=key, defaults={"value": value})
            if not (setting.description or "").strip():
                setting.description = DEFAULT_SETTING_DESCRIPTIONS.get(key, "")
                setting.save(update_fields=["description"])
    except (OperationalError, ProgrammingError):
        # Database isn't ready yet (e.g., during migrations).
        return


def ensure_default_groups() -> None:
    try:
        for name in ["Greeter", "Admin", "Pastor"]:
            Group.objects.get_or_create(name=name)
    except (OperationalError, ProgrammingError):
        return


def get_setting(key: str, default: str = "") -> str:
    setting = SystemSetting.objects.filter(key=key).first()
    if setting and setting.value is not None:
        return setting.value
    return DEFAULT_SETTINGS.get(key, default)
