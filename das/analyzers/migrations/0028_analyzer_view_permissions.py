# Generated by Django 2.0.2 on 2018-08-15 19:10

from django.db import migrations


def forward_f(apps, schema_editor):
    '''
    Add Permission sets for analyzer configuration.
    :param apps:
    :param schema_editor:
    :return:
    '''
    PermissionSet = apps.get_model('accounts', 'PermissionSet')
    Permission = apps.get_model('auth', 'Permission')

    db_alias = schema_editor.connection.alias

    # Add for administrators
    a_ps, created = PermissionSet.objects.using(
        db_alias).get_or_create(name='Analyzer Admin Permissions')

    permission_codenames = [f'{p}_geofenceanalyzerconfig' for p in ('view', 'add', 'change', 'delete',)]
    geofence_permissions = Permission.objects.using(
        db_alias).filter(codename__in=permission_codenames)
    geofence_ps, created = PermissionSet.objects.using(
        db_alias).get_or_create(name='Geofence Analyzer Admin Permisssions')
    geofence_ps.permissions.add(*geofence_permissions)

    permission_codenames = [f'{p}_proximityanalyzerconfig' for p in ('view', 'add', 'change', 'delete',)]
    proximity_permissions = Permission.objects.using(
        db_alias).filter(codename__in=permission_codenames)
    proximity_ps, created = PermissionSet.objects.using(
        db_alias).get_or_create(name='Proximity Analyzer Admin Permisssions')
    proximity_ps.permissions.add(*proximity_permissions)

    proximity_ps.children.add(a_ps)
    geofence_ps.children.add(a_ps)

    # Add for viewers
    a_ps, created = PermissionSet.objects.using(
        db_alias).get_or_create(name='Analyzer View Permissions')

    permission_codenames = [f'{p}_geofenceanalyzerconfig' for p in ('view',)]
    geofence_permissions = Permission.objects.using(
        db_alias).filter(codename__in=permission_codenames)
    geofence_ps, created = PermissionSet.objects.using(
        db_alias).get_or_create(name='Geofence Analyzer View Permisssions')
    geofence_ps.permissions.add(*geofence_permissions)

    permission_codenames = [f'{p}_proximityanalyzerconfig' for p in ('view',)]
    proximity_permissions = Permission.objects.using(
        db_alias).filter(codename__in=permission_codenames)
    proximity_ps, created = PermissionSet.objects.using(
        db_alias).get_or_create(name='Proximity Analyzer View Permisssions')
    proximity_ps.permissions.add(*proximity_permissions)

    proximity_ps.children.add(a_ps)
    geofence_ps.children.add(a_ps)


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0027_remove_geofences_property'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='geofenceanalyzerconfig',
            options={'permissions': (
                ('view_geofenceanalyzerconfig', 'Can view Geofence Analyzer configurations'),)},
        ),
        migrations.AlterModelOptions(
            name='proximityanalyzerconfig',
            options={'permissions': (
                ('view_proximityanalyzerconfig', 'Can view Proximity Analyzer Configurations'),)},
        ),
        migrations.RunPython(
            code=forward_f,
            reverse_code=migrations.RunPython.noop
        )
    ]