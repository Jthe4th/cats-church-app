from django.db import migrations


def update_label_size_descriptions(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    descriptions = {
        "printnode_label_width_in": "Printed label width in inches for browser and PrintNode output. Use 2.440 for Brother QL 2.4-inch black/red media.",
        "printnode_label_height_in": "Printed label height in inches for browser and PrintNode output. Use 1.100 for a fixed 1.1-inch Brother QL black/red label length.",
        "printnode_label_margin_in": "Printed label inner margin in inches for browser and PrintNode output.",
    }
    for key, description in descriptions.items():
        SystemSetting.objects.filter(key=key).update(description=description)
    SystemSetting.objects.filter(
        key="printnode_label_width_in",
        value__in=["2.4", "2.40", "2.441", "3.5", "3.50"],
    ).update(value="2.440")
    SystemSetting.objects.filter(
        key="printnode_label_height_in",
        value__in=["1.10", "1.102", "1.137", "1.14", "3.937"],
    ).update(value="1.1")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_seed_printnode_label_size_settings"),
    ]

    operations = [
        migrations.RunPython(update_label_size_descriptions, migrations.RunPython.noop),
    ]
