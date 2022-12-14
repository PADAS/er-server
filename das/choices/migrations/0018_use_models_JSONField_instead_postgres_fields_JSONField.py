# Generated by Django 3.1 on 2022-06-22 19:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('choices', '0017_choices_timestamps_update'),
    ]

    operations = [
        migrations.AlterField(
            model_name='choice',
            name='model',
            field=models.CharField(choices=[('activity.event', 'Field Reports'), ('activity.eventtype', 'Field Report Type'), ('mapping.TileLayer', 'Maps'), (
                'observations.region', 'Region'), ('observations.Source', 'Sources'), ('accounts.user.User', 'User')], default='activity.event', max_length=50),
        ),
    ]
