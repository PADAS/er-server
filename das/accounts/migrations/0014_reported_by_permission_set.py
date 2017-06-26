from django.db import migrations
from django.core.management import call_command
from django.contrib.auth.management import create_permissions


def create_reported_by_permission_set(apps, schema_editor):
    apps.models_module = True
    create_permissions(apps, verbosity=0)
    apps.models_module = None
    call_command('loaddata', 'reported_by_permission_set')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_profiles'),
    ]

    operations = [
        migrations.RunPython(create_reported_by_permission_set),
    ]
