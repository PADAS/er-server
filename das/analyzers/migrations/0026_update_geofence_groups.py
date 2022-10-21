# Generated by Django 2.0.2 on 2018-08-13 20:29

from django.db import migrations
from django.contrib.contenttypes.models import ContentType


def forward_f(apps, schema_editor):
    '''
    '''
    GeofenceAnalyzerConfig = apps.get_model(
        'analyzers', 'GeofenceAnalyzerConfig')
    SpatialFeatureGroupStatic = apps.get_model(
        'mapping', 'SpatialFeatureGroupStatic')

    db_alias = schema_editor.connection.alias

    for geofence_analyzer in GeofenceAnalyzerConfig.objects.using(db_alias).all():

        if geofence_analyzer.geofences is not None:

            old_name = geofence_analyzer.geofences.name
            old_description = geofence_analyzer.geofences.description

            critical_features = geofence_analyzer.geofences.features.filter(
                feature_type__name='Geofence_Primary')
            if critical_features:
                critical_geofence_group, created = SpatialFeatureGroupStatic.objects.get_or_create(
                    name='{} (critical)'.format(old_name), description=old_description)
                critical_geofence_group.features.clear()
                critical_geofence_group.features.add(*critical_features)
                critical_geofence_group.save()
                geofence_analyzer.critical_geofence_group = critical_geofence_group
                # print(f'Critical Fence Group:
                # {geofence_analyzer.critical_geofence_group.features.all()}')

            warning_features = geofence_analyzer.geofences.features.filter(
                feature_type__name='Geofence_Warning')
            if warning_features:
                warning_geofence_group, created = SpatialFeatureGroupStatic.objects.get_or_create(
                    name='{} (warning)'.format(old_name), description=old_description)
                warning_geofence_group.features.clear()
                warning_geofence_group.features.add(*warning_features)
                warning_geofence_group.save()
                geofence_analyzer.warning_geofence_group = warning_geofence_group
                # print(f'Warning Fence Group:
                # {geofence_analyzer.warning_geofence_group.features.all()}')

            geofence_analyzer.save()


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0025_split_geofence_groups'),
    ]

    operations = [

        migrations.RunPython(
            code=forward_f, reverse_code=migrations.RunPython.noop),
        # migrations.RemoveField(
        #     model_name='geofenceanalyzerconfig',
        #     name='geofences',
        # ),
    ]
