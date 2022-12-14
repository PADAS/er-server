# Generated by Django 2.2.24 on 2022-04-21 15:46

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0118_add_stationary_subjects_lora_gategay_and_radio_repeater'),
    ]

    operations = [
        migrations.CreateModel(
            name='LatestObservationSource',
            fields=[
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='last_observation_sources',
                 related_query_name='last_observation_source', serialize=False, to='observations.Source', unique=True)),
                ('recorded_at', models.DateTimeField()),
                ('observation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to='observations.Observation')),
            ],
        ),
    ]
