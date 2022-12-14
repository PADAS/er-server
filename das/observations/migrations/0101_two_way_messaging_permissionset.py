# Generated by Django 2.2.9 on 2021-04-20 09:49

from django.db import migrations


def forwards(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    PermissionSet = apps.get_model('accounts', 'PermissionSet')

    db_alias = schema_editor.connection.alias

    ps, _ = PermissionSet.objects.using(db_alias).get_or_create(name='Full Access Message Permissions')
    message_codenames = [f'{codename}_message' for codename in ('add', 'change', 'delete', 'view')]
    message_permission = Permission.objects.using(db_alias).filter(codename__in=message_codenames)
    ps.permissions.add(*message_permission)

    # Message Permission - Readonly
    ps, _ = PermissionSet.objects.using(db_alias).get_or_create(name='View Message Permission')
    message_permission = Permission.objects.using(db_alias).filter(codename='view_message')
    ps.permissions.add(*message_permission)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0100_vultures_subtypes'),
    ]

    operations = [
        migrations.RunPython(code=forwards, reverse_code=migrations.RunPython.noop)
    ]

