from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_seed_printnode_settings"),
    ]

    operations = [
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
                    ("database_backup", "Database Backup"),
                    ("database_restore", "Database Restore"),
                    ("service_close", "Service Close"),
                    ("service_reopen", "Service Reopen"),
                    ("setting_change", "Setting Change"),
                ],
                max_length=40,
            ),
        ),
    ]
