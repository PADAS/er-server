# Generated by Django 2.2.14 on 2020-10-05 21:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0102_done_and_cancelled_states'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='patrolsegment',
            name='state',
        ),
        migrations.AlterField(
            model_name='patrol',
            name='state',
            field=models.CharField(choices=[('open', 'Open'), ('done', 'Done'), ('cancelled', 'Cancelled')], default='open', max_length=25),
        ),
    ]
