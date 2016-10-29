# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

def update_source_provider_name(apps, schema_editor):

    '''
    I've added provider_name to Source, so I want to populate it appropriately for existing records.

    For some, we can pull apart model name which.

    For Sources associated with a Plugin, we'll use the plugin's name.
    '''

    Source = apps.get_model('observations', 'Source')

    for src in Source.objects.filter(model_name__startswith='gsat'):
        v = src.model_name.split(':')
        if len(v) == 2:
            src.provider_name = v[1]
            src.model_name = v[0]
            src.save()

    for src in Source.objects.filter(model_name__startswith='dasradioagent'):
        v = src.model_name.split(':')
        if len(v) == 2:
            src.provider_name = v[1]
            src.model_name = v[0]
            src.save()


    SourcePlugin = apps.get_model('tracking', 'sourceplugin')
    plugin_models = [apps.get_model('tracking', name) for name in ('SavannahPlugin',
                                                                   'DemoSourcePlugin',
                                                                   'InreachPlugin',
                                                                   'InreachKMLPlugin',
                                                                   'AWTHttpPlugin',
                                                                   'SkygisticsSatellitePlugin',
                                                                   'FirmsPlugin',
                                                                   'SpiderTracksPlugin',
                                                                   )]

    for plugin_model in plugin_models:
        plugins = plugin_model.objects.all()
        for plugin in plugins:
            source_plugins = SourcePlugin.objects.filter(plugin_id=plugin.id)
            for sp in source_plugins:
                src = sp.source
                src.provider_name = plugin.name
                src.save()


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0020_source_timestamped'),
        ('tracking', '0002_spidertracksplugin'),
    ]

    operations = [
        migrations.RunPython(update_source_provider_name),
    ]
