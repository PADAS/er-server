# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0004_regions_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='region',
            name='slug',
            field=models.SlugField(max_length=100, unique=True),
        ),
    ]
