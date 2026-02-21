from django.db import migrations


def seed_kiosk_logo_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    defaults = {
        "kiosk_logo_path": ("/static/img/EC-SDA-Church_Stacked_Final.png", "Logo image shown on kiosk screens."),
        "kiosk_logo_width_px": ("200", "Logo width in pixels for kiosk screens."),
        "kiosk_logo_height_px": ("", "Logo height in pixels for kiosk screens. Leave blank for auto height."),
    }
    for key, (value, description) in defaults.items():
        obj, created = SystemSetting.objects.get_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )
        if not created and not (obj.description or "").strip():
            obj.description = description
            obj.save(update_fields=["description"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_auditlog"),
    ]

    operations = [
        migrations.RunPython(seed_kiosk_logo_settings, migrations.RunPython.noop),
    ]
