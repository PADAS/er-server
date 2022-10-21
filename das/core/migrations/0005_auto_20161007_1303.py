# -*- coding: utf-8 -*-
# Generated by Django 1.9.9 on 2016-10-07 13:03
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_actiontaken_behavior_causeofdeath_color_conservancy_fencesection_health_species_station'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ActionTaken',
        ),
        migrations.DeleteModel(
            name='Behavior',
        ),
        migrations.DeleteModel(
            name='CauseOfDeath',
        ),
        migrations.AlterUniqueTogether(
            name='choice',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='choice',
            name='sub_choice_of',
        ),
        migrations.DeleteModel(
            name='Color',
        ),
        migrations.DeleteModel(
            name='Conservancy',
        ),
        migrations.DeleteModel(
            name='DynamicChoice',
        ),
        migrations.DeleteModel(
            name='FenceSection',
        ),
        migrations.DeleteModel(
            name='Health',
        ),
        migrations.DeleteModel(
            name='Species',
        ),
        migrations.DeleteModel(
            name='Station',
        ),
        migrations.DeleteModel(
            name='Choice',
        ),
    ]