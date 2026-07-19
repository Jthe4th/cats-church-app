from django.db import migrations


SETTINGS = {
    "printer_profiles": {
        "value": "{}",
        "description": "Reusable printer profile definitions. Profiles can store a backend, printer target, label size, and media settings.",
    },
    "kiosk_printer_profile_map": {
        "value": "{}",
        "description": 'JSON object mapping kiosk ids to printer profile names, e.g. {"kiosk1": "front-desk-brother"}.',
    },
}


def seed_printer_profile_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    for key, defaults in SETTINGS.items():
        setting, created = SystemSetting.objects.get_or_create(key=key, defaults=defaults)
        if not created and not (setting.description or "").strip():
            setting.description = defaults["description"]
            setting.save(update_fields=["description"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0021_remove_label_font_source_setting"),
    ]

    operations = [
        migrations.RunPython(seed_printer_profile_settings, migrations.RunPython.noop),
    ]
