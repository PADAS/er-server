# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-11-02 15:30
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('choices', '0002_auto_20161007_1417'),
    ]

    operations = [
        migrations.AlterField(
            model_name='actiontaken',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='behavior',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='causeofdeath',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='color',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='conservancy',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='contacttype',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='fencesection',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='health',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='illegalactivity',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='livestock',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='poachingmean',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='sectionarea',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='species',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='station',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='team',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='tribe',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='trophystatus',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='wildlifegap',
            name='ordernum',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
