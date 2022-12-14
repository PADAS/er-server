# Generated by Django 2.0.1 on 2018-03-09 23:27

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.query_utils
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0067_fix-perm-name-error'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventFilter',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('ordernum', models.SmallIntegerField(
                    default=0, verbose_name='Sort order number')),
                ('is_hidden', models.BooleanField(
                    default=True, verbose_name='Hide this filter')),
                ('filter_name', models.CharField(max_length=100,
                                                 verbose_name='Display name that is meaningful to a user')),
                ('filter_spec', django.contrib.postgres.fields.jsonb.JSONField(
                    default='{}', verbose_name='Filter specification')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
