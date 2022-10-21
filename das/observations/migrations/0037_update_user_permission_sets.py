from __future__ import unicode_literals

from django.core.management import call_command
from django.db import migrations

from accounts.models import PermissionSet, User
from utils.models import create_all_permissions, update_all_contenttypes


def update_user_permission_sets():
    all_time_group = PermissionSet.objects.get(
        id='cfa2b7b3-4bae-42f3-8691-b119da54af4e')
    restricted_time_group = PermissionSet.objects.get(
        id='e8211a8b-226e-44bf-8235-598a67427348')

    for user in User.objects.all():
        if user.permission_sets.filter(name='view_realtime').exists():
            user.permission_sets.add(all_time_group)
        else:
            user.permission_sets.add(restricted_time_group)
        user.save()


def forward(apps, schema_editor):
    call_command('loaddata', 'new_permission_sets', app_label='observations')

    update_all_contenttypes()
    create_all_permissions()

    update_user_permission_sets()


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0036_access_ends_1'),

    ]

    operations = [
        migrations.RunPython(forward, backward)
    ]
