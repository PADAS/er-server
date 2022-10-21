# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0003_regions'),
    ]

    operations = [
        migrations.AddField(
            model_name='region',
            name='slug',
            field=models.SlugField(default=uuid.uuid4, max_length=100),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='region',
            unique_together=set([]),
        ),
    ]
