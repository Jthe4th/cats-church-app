from django.db import migrations


def seed_printnode_label_size_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    defaults = {
        "printnode_label_width_in": (
            "3.5",
            "PrintNode PDF label width in inches. Use 3.5 for Brother DK-1201 address labels or 2.4 for 62mm continuous labels.",
        ),
        "printnode_label_height_in": (
            "1.14",
            "PrintNode PDF label height in inches. Use 1.14 for Brother DK-1201 address labels or 1.1 for short continuous labels.",
        ),
        "printnode_label_margin_in": (
            "0.08",
            "PrintNode PDF label margin in inches.",
        ),
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
        ("core", "0016_alter_auditlog_action_member_import"),
    ]

    operations = [
        migrations.RunPython(seed_printnode_label_size_settings, migrations.RunPython.noop),
    ]
