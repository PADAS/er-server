# Generated by Django 3.1 on 2022-06-22 19:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzers', '0040_add_quite_period_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='environmentalsubjectanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='featureproximityanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='geofenceanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='globalforestwatchsubscription',
            name='additional',
            field=models.JSONField(
                blank=True, default=dict, help_text='JSON data for subscriptions'),
        ),
        migrations.AlterField(
            model_name='immobilityanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='lowspeedpercentileanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='lowspeedwilcoxanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='speeddistro',
            name='percentiles',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='subjectanalyzerresult',
            name='values',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='subjectproximityanalyzerconfig',
            name='additional',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
