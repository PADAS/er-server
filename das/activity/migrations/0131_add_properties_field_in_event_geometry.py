# Generated by Django 3.1 on 2022-08-19 20:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0130_create_event_geometry_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventgeometry',
            name='properties',
            field=models.JSONField(default=dict),
        ),
    ]
