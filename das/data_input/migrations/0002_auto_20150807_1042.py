# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('data_input', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pluginconf',
            name='created_at',
        ),
        migrations.AddField(
            model_name='pluginconf',
            name='create_datetime',
            field=models.DateTimeField(auto_now_add=True, default=datetime.datetime(2015, 8, 7, 17, 42, 27, 266108, tzinfo=utc)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pluginconf',
            name='last_modified_datetime',
            field=models.DateTimeField(default=datetime.datetime(2015, 8, 7, 17, 42, 32, 308908, tzinfo=utc), auto_now=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='pluginconf',
            name='plugin_name',
            field=models.CharField(default='', max_length=100, verbose_name='plugin name'),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='pluginconfsource',
            unique_together=set([('plugin_conf', 'source')]),
        ),
    ]
