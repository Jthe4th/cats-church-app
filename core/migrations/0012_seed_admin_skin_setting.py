from django.db import migrations


def seed_admin_skin_setting(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    key = "admin_skin"
    value = "default"
    description = "Jazzmin/Bootswatch skin used in the admin area."
    obj, created = SystemSetting.objects.get_or_create(
        key=key,
        defaults={"value": value, "description": description},
    )
    updated_fields = []
    if not created and not (obj.value or "").strip():
        obj.value = value
        updated_fields.append("value")
    if not created and not (obj.description or "").strip():
        obj.description = description
        updated_fields.append("description")
    if updated_fields:
        obj.save(update_fields=updated_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_seed_label_scale_settings"),
    ]

    operations = [
        migrations.RunPython(seed_admin_skin_setting, migrations.RunPython.noop),
    ]
