# Generated by Django 2.0.2 on 2018-10-08 21:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0017_blanks'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='tilelayer',
            name='maps',
        ),
        migrations.RemoveField(
            model_name='tilelayer',
            name='tile_type',
        ),
        migrations.RemoveField(
            model_name='tilelayer',
            name='version',
        ),
        migrations.AddField(
            model_name='tilelayer',
            name='ordernum',
            field=models.SmallIntegerField(blank=True, null=True),
        ),
    ]
