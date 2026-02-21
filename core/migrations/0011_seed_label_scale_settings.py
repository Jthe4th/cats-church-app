from django.db import migrations


def seed_label_scale_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    defaults = {
        "label_first_name_scale": ("100", 'Scale first-name text size on labels as a percentage (100 = default).'),
        "label_last_name_scale": ("100", 'Scale last-name text size on labels as a percentage (100 = default).'),
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
        ("core", "0010_seed_kiosk_logo_settings"),
    ]

    operations = [
        migrations.RunPython(seed_label_scale_settings, migrations.RunPython.noop),
    ]
