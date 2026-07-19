from django.db import migrations


def remove_label_font_source_setting(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    SystemSetting.objects.filter(key="label_font_source").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_seed_brother_label_media_setting"),
    ]

    operations = [
        migrations.RunPython(remove_label_font_source_setting, migrations.RunPython.noop),
    ]
