# Generated by Django 2.2.14 on 2020-10-16 12:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0104_patrols_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='patrolsegment',
            name='scheduled_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
