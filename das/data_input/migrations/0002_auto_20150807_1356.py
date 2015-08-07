# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('data_input', '0001_squashed_0002_auto_20150807_1042'),
    ]

    operations = [
        migrations.RenameField(
            model_name='pluginconf',
            old_name='create_datetime',
            new_name='created_at',
        ),
        migrations.RenameField(
            model_name='pluginconf',
            old_name='last_modified_datetime',
            new_name='updated_at',
        ),
    ]
