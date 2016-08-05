# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.core.management import call_command
from django.contrib.auth.management import create_permissions


def populate_eventtype(apps, schema_editor):
    #initial data references permissions
    apps.models_module = True
    create_permissions(apps, verbosity=0)
    apps.models_module = None
    call_command('loaddata', 'initial_eventtype')



class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0031_subject_active'),
    ]

    operations = [
        migrations.RunPython(populate_eventtype),
    ]
