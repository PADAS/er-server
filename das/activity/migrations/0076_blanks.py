# Generated by Django 2.0.6 on 2018-09-30 13:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0075_eventtype-default_state'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='sort_at',
            field=models.DateTimeField(blank=True),
        ),
    ]
