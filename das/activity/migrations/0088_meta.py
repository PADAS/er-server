# Generated by Django 2.2.11 on 2020-05-16 13:53

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0087_update_tsvector_id'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='community',
            options={'verbose_name': 'Event Reporters', 'verbose_name_plural': 'Event Reporters'},
        ),
        migrations.AlterModelOptions(
            name='eventcategory',
            options={'verbose_name': 'Event Category', 'verbose_name_plural': 'Event Categories'},
        ),
        migrations.AlterField(
            model_name='event',
            name='priority',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Gray'), (100, 'Green'), (200, 'Amber'), (300, 'Red')], default=0),
        ),
        migrations.AlterField(
            model_name='eventclassfactor',
            name='priority',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Gray'), (100, 'Green'), (200, 'Amber'), (300, 'Red')], default=100),
        ),
        migrations.AlterField(
            model_name='eventfilter',
            name='filter_spec',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict, verbose_name='Filter specification'),
        ),
        migrations.AlterField(
            model_name='eventnotification',
            name='method',
            field=models.CharField(choices=[('email', 'Email'), ('sms', 'SMS'), ('whatsapp', 'WhatsApp')], default='email', max_length=20),
        ),
        migrations.AlterField(
            model_name='eventtype',
            name='default_priority',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Gray'), (100, 'Green'), (200, 'Amber'), (300, 'Red')], default=0),
        ),
        migrations.AlterField(
            model_name='eventtype',
            name='schema',
            field=models.TextField(blank=True, default='{\n                "schema":\n                {\n                    "$schema": "http://json-schema.org/draft-04/schema#",\n                    "title": "Empty Event Schema",\n                    "type": "object",\n                    "properties": {}\n                },\n                "definition": []\n                }'),
        ),
        migrations.AlterField(
            model_name='notificationmethod',
            name='method',
            field=models.CharField(choices=[('email', 'Email'), ('sms', 'SMS'), ('whatsapp', 'WhatsApp')], default='email', max_length=20),
        ),
        migrations.AddIndex(
            model_name='eventnotification',
            index=models.Index(fields=['event'], name='activity_ev_event_i_172cfd_idx'),
        ),
    ]
