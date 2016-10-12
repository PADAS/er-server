# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.core.management import call_command


def populate_features(apps, schema_editor):
    apps.models_module = None
    #call_command('loaddata', 'initial_features')


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0003_featuresets'),
    ]

    operations = [
        migrations.RunPython(populate_features),
    ]
