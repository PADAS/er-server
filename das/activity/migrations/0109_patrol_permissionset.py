# Generated by Django 2.2.9 on 2020-12-15 02:02

from django.db import migrations


def patrol_managements_permissionset(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    PermissionSet = apps.get_model('accounts', 'PermissionSet')

    db_alias = schema_editor.connection.alias

    ps, _ = PermissionSet.objects.using(db_alias).get_or_create(name='Full Patrols Permissions')
    patrol_codenames = [f'{codename}_patrol' for codename in ('add', 'change', 'delete', 'view')]
    patroltype_codenames = [f'{codename}_patroltype' for codename in ('add', 'change', 'delete', 'view')]

    patrol_codenames.extend(patroltype_codenames)
    patrols_permission = Permission.objects.using(db_alias).filter(codename__in=patrol_codenames)
    ps.permissions.add(*patrols_permission)

    # Patrol_Permission - No delete
    ps, _ = PermissionSet.objects.using(db_alias).get_or_create(name='Patrols Permissions - No Delete')
    patrol_codenames = [f'{codename}_patrol' for codename in ('add', 'change', 'view')]
    patrols_permission = Permission.objects.using(db_alias).filter(codename__in=patrol_codenames)
    ps.permissions.add(*patrols_permission)

    # View Patrol Permissions
    ps, _ = PermissionSet.objects.using(db_alias).get_or_create(name='View Patrols Permissions')
    patrols_permission = Permission.objects.using(db_alias).filter(codename='view_patrol')
    ps.permissions.add(*patrols_permission)


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0108_patrol_segment_report'),
    ]

    operations = [
        migrations.RunPython(code=patrol_managements_permissionset,
                             reverse_code=migrations.RunPython.noop)
    ]
