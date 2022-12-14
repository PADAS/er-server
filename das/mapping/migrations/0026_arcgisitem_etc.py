# Generated by Django 2.2.9 on 2020-03-14 08:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0025_arcgisconfiguration_arcgisgroup'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='featureset',
            options={'ordering': ['name']},
        ),
        migrations.AlterModelOptions(
            name='featuretype',
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='spatialfeaturefile',
            name='status',
            field=models.CharField(blank=True, max_length=1000, null=True, verbose_name='Feature Load Status'),
        ),
        migrations.AddField(
            model_name='spatialfile',
            name='status',
            field=models.CharField(blank=True, max_length=1000, null=True, verbose_name='Feature Load Status'),
        ),
        migrations.AlterField(
            model_name='arcgisconfiguration',
            name='id_field',
            field=models.CharField(blank=True, default='GlobalID', help_text='Name of field in your GIS data that has the feature ID. Default is GlobalID', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='arcgisconfiguration',
            name='name_field',
            field=models.CharField(blank=True, default='Name', help_text='Name of field in your GIS data that has the feature name. Default is Name', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='arcgisconfiguration',
            name='type_label',
            field=models.CharField(blank=True, default='FeatureType', help_text='Name of field in your GIS data that has the feature type. Defaults are Type and FeatureType', max_length=100, null=True, verbose_name='Type field'),
        ),
        migrations.CreateModel(
            name='ArcgisItem',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=50)),
                ('arcgis_config', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='mapping.ArcgisConfiguration')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='spatialfeature',
            name='arcgis_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='mapping.ArcgisItem'),
        ),
    ]
