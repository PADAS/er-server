# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='subject_type',
            field=models.CharField(choices=[('wildlife', 'Wildlife'), ('vehicle', 'Vehicle'), ('stationary-object', 'Stationary Object')], default='wildlife', max_length=100),
        ),
    ]
