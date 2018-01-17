from django.db import migrations
from django.core.management import call_command
import utils.models


def create_reported_by_permission_set(apps, schema_editor):
    utils.models.migrate_permissions(apps)
    call_command('loaddata', 'reported_by_permission_set')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_profiles'),
    ]

    operations = [
        migrations.RunPython(create_reported_by_permission_set),
    ]
