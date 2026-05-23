from django.db import migrations, models


def seed_server_printer_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    defaults = {
        "server_printer_map": (
            "{}",
            'JSON object mapping kiosk ids to network printer addresses, e.g. {"kiosk1": "192.168.1.50:9100"}.',
        ),
        "server_printer_timeout_seconds": (
            "10",
            "Connection timeout for server-side network printer jobs.",
        ),
    }
    for key, (value, description) in defaults.items():
        setting, created = SystemSetting.objects.get_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )
        if not created and not setting.description:
            setting.description = description
            setting.save(update_fields=["description"])
    SystemSetting.objects.filter(key="print_mode").update(
        description="Choose whether kiosks print through the connected browser printer, PrintNode, or server-side network printing."
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_update_label_size_setting_descriptions"),
    ]

    operations = [
        migrations.RunPython(seed_server_printer_settings, migrations.RunPython.noop),
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
                    ("server_print_success", "Server Print Success"),
                    ("server_print_failure", "Server Print Failure"),
                    ("database_backup", "Database Backup"),
                    ("database_restore", "Database Restore"),
                    ("member_import", "Member Import"),
                    ("service_close", "Service Close"),
                    ("service_reopen", "Service Reopen"),
                    ("setting_change", "Setting Change"),
                ],
                max_length=40,
            ),
        ),
    ]
