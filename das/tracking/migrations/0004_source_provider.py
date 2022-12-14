# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2017-02-09 21:41
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import observations.models


plugin_table_names = ['tracking_{}'.format(plugin_name) for plugin_name in ('awetelemetryplugin', 'awthttpplugin',
                                                                            'demosourceplugin', 'firmsplugin',
                                                                            'inreachkmlplugin', 'inreachplugin',
                                                                            'savannahplugin',
                                                                            'skygisticssatelliteplugin',
                                                                            'spidertracksplugin',)]
SOURCE_PROVIDER_UPDATE = '''with provider as (select id, provider_key from observations_sourceprovider)
                   update {0} p
                      set provider_id = provider.id
                     from provider
                    where provider.provider_key    = p.name;
                    '''

ALL_UPDATES = ';'.join([SOURCE_PROVIDER_UPDATE.format(pn)
                        for pn in plugin_table_names])


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0030_source_provider'),
        ('tracking', '0003_awetelemetryplugin'),
    ]

    operations = [
        migrations.AddField(
            model_name='awetelemetryplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='awthttpplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='demosourceplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='firmsplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='inreachkmlplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='inreachplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='savannahplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='skygisticssatelliteplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AddField(
            model_name='spidertracksplugin',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id,
                                    on_delete=django.db.models.deletion.CASCADE, related_name='+', to='observations.SourceProvider'),
        ),
        migrations.AlterField(
            model_name='awetelemetryplugin',
            name='service_url',
            field=models.CharField(
                help_text='The API endpoint for the AWE Telemetry/AWT service.', max_length=50),
        ),
        migrations.RunSQL(sql=ALL_UPDATES, reverse_sql=migrations.RunSQL.noop),
    ]
