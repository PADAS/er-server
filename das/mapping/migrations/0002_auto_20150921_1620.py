# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_pgjson.fields


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='linefeature',
            name='description',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='linefeature',
            name='name',
            field=models.CharField(default='', unique=True, max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='linefeature',
            name='presentation',
            field=django_pgjson.fields.JsonBField(default={}),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='linefeature',
            name='type',
            field=models.CharField(default='', max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pointfeature',
            name='description',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='pointfeature',
            name='name',
            field=models.CharField(default='', unique=True, max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pointfeature',
            name='presentation',
            field=django_pgjson.fields.JsonBField(default={}),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pointfeature',
            name='type',
            field=models.CharField(default='', max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='polygonfeature',
            name='description',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='polygonfeature',
            name='name',
            field=models.CharField(default='', unique=True, max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='polygonfeature',
            name='presentation',
            field=django_pgjson.fields.JsonBField(default={}),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='polygonfeature',
            name='type',
            field=models.CharField(default='', max_length=80),
            preserve_default=False,
        ),
    ]
