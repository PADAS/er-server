# Generated by Django 2.2.9 on 2021-04-08 12:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0118_update_revision'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventtype',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
