# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-10-07 14:17
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('choices', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='IllegalActivity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Livestock',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='PoachingMean',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='SectionArea',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Tribe',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='TrophyStatus',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='WildlifeGap',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True)),
            ],
        ),
        migrations.RenameField(
            model_name='actiontaken',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='behavior',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='causeofdeath',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='color',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='conservancy',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='fencesection',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='health',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='species',
            old_name='order',
            new_name='ordernum',
        ),
        migrations.RenameField(
            model_name='station',
            old_name='order',
            new_name='ordernum',
        ),
    ]