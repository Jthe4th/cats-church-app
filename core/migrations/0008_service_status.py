from datetime import date

from django.db import migrations, models


def close_past_services(apps, schema_editor):
    Service = apps.get_model("core", "Service")
    Service.objects.filter(date__lt=date.today()).update(status="closed")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_person_confidential_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="status",
            field=models.CharField(
                choices=[("open", "Open"), ("closed", "Closed")],
                default="open",
                max_length=10,
            ),
        ),
        migrations.RunPython(close_past_services, migrations.RunPython.noop),
    ]
