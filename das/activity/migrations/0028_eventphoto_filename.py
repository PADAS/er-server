# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-07-12 00:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0027_photorevision'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventphoto',
            name='filename',
            field=models.TextField(default='noname', verbose_name='Name of uploaded image file.'),
        ),
    ]
