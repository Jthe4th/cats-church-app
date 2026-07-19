from django.db import migrations


def seed_brother_label_media_setting(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    SystemSetting.objects.get_or_create(
        key="brother_label_media",
        defaults={
            "value": "62red",
            "description": "Brother QL media mode for silent raw printing. Use 62 for plain 62mm media or 62red for black/red/white media.",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_seed_server_printer_settings"),
    ]

    operations = [
        migrations.RunPython(seed_brother_label_media_setting, migrations.RunPython.noop),
    ]
