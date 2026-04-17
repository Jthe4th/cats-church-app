from django.db import migrations, models


def seed_printnode_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    defaults = {
        "print_mode": (
            "Connected Printer",
            "Choose whether kiosks print through the connected browser printer or PrintNode silent printing.",
        ),
        "printnode_api_key": (
            "",
            "PrintNode API key used for silent kiosk printing.",
        ),
        "printnode_printer_map": (
            "{}",
            'JSON object mapping kiosk ids to PrintNode printer ids, e.g. {"kiosk1": "123456"}.',
        ),
    }
    for key, (value, description) in defaults.items():
        obj, created = SystemSetting.objects.get_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )
        updated_fields = []
        if not created and not (obj.description or "").strip():
            obj.description = description
            updated_fields.append("description")
        if updated_fields:
            obj.save(update_fields=updated_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_person_created_at_alter_auditlog_action"),
    ]

    operations = [
        migrations.RunPython(seed_printnode_settings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("checkin", "Check-in"),
                    ("undo_checkin", "Undo Check-in"),
                    ("print_nametag", "Print Nametag"),
                    ("printnode_success", "PrintNode Success"),
                    ("printnode_failure", "PrintNode Failure"),
                    ("service_close", "Service Close"),
                    ("service_reopen", "Service Reopen"),
                    ("setting_change", "Setting Change"),
                ],
                max_length=40,
            ),
        ),
    ]
