from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_profiles"),
    ]

    operations = [
        # migrations.RunPython(create_reported_by_permission_set),   Move to accounts 0031
    ]
