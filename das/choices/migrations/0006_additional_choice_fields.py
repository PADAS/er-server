# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2017-03-05 20:09
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('choices', '0005_choices_updates'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArrestViolation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Arrest Violation',
                'verbose_name_plural': 'Arrest Violations',
            },
        ),
        migrations.CreateModel(
            name='Nationality',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Nationality',
                'verbose_name_plural': 'Nationalities',
            },
        ),
        migrations.CreateModel(
            name='Village',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('ordernum', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Village',
                'verbose_name_plural': 'Villages',
            },
        ),
    ]
