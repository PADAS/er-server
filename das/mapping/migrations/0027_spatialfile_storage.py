# Generated by Django 2.2.9 on 2020-03-23 16:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0026_arcgisitem_etc'),
    ]

    operations = [
        migrations.AlterField(
            model_name='spatialfeaturefile',
            name='data',
            field=models.FileField(upload_to='mapping/spatialfiles'),
        ),
        migrations.AlterField(
            model_name='spatialfeaturefile',
            name='feature_types_file',
            field=models.FileField(blank=True, null=True, upload_to='mapping/spatialfiles'),
        ),
        migrations.AlterField(
            model_name='spatialfile',
            name='data',
            field=models.FileField(upload_to='mapping/spatialfiles'),
        ),
    ]
