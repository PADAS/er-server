# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-05-23 16:52
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0015_analyzers_refactor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subjectanalyzerresult',
            name='estimated_time',
            field=models.DateTimeField(),
        ),
    ]
