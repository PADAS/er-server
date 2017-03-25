# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.core.management import call_command


def populate_localmap(apps, schema_editor):
    apps.models_module = None
    call_command('loaddata', 'initial_dev_map')


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0008_featuretype'),
    ]

    operations = [
        migrations.RunPython(populate_localmap),
    ]
