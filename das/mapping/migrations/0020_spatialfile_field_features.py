# Generated by Django 2.0.13 on 2019-11-28 13:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0019_bump_name_length'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='displaycategory',
            options={'verbose_name': 'Display Category', 'verbose_name_plural': 'Display Categories'},
        ),
        migrations.AddField(
            model_name='linefeature',
            name='spatialfile',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='mapping.SpatialFile'),
        ),
        migrations.AddField(
            model_name='pointfeature',
            name='spatialfile',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='mapping.SpatialFile'),
        ),
        migrations.AddField(
            model_name='polygonfeature',
            name='spatialfile',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='mapping.SpatialFile'),
        ),
        migrations.AlterField(
            model_name='spatialfile',
            name='name',
            field=models.CharField(max_length=255, unique=True, verbose_name='Spatial File'),
        ),
    ]
