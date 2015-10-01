# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import uuid
import django.contrib.postgres.fields

class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PluginConf',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, serialize=False, primary_key=True)),
                ('plugin_name', models.CharField(max_length=100, null=True, verbose_name='Plugin Name')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('configuration', django.contrib.postgres.fields.JSONField()),
            ],
        ),

        migrations.CreateModel(
            name='PluginConfSource',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, serialize=False, primary_key=True)),
                ('plugin_conf', models.ForeignKey(to='data_input.PluginConf')),
                ('source', models.ForeignKey(to='observations.Source')),
                ('additional', django.contrib.postgres.fields.JSONField()),
            ],
        ),

        migrations.AlterUniqueTogether(
            name='pluginconfsource',
            unique_together=set([('plugin_conf', 'source')]),
        ),

    ]
