# Generated by Django 2.0.13 on 2019-12-12 12:28

from django.db import migrations, models
import tagulous.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0020_spatialfile_field_features'),
    ]

    operations = [
        migrations.AlterField(
            model_name='spatialfeaturetype',
            name='tags',
            field=tagulous.models.fields.TagField(_set_tag_meta=True, blank=True, help_text='Enter a comma-separated tag string', to='mapping.SpatialFeatureTypeTag'),
        ),
        migrations.AlterField(
            model_name='spatialfile',
            name='name',
            field=models.CharField(max_length=255, unique=True, verbose_name='SpatialFile Name'),
        ),
    ]
