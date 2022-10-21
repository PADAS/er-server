# Generated by Django 2.0.1 on 2018-01-18 22:01

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0012_tagulous_rename'),
    ]

    operations = [
        migrations.AlterField(
            model_name='linefeature',
            name='featureset',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, to='mapping.FeatureSet'),
        ),
        migrations.AlterField(
            model_name='linefeature',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to='mapping.FeatureType'),
        ),
        migrations.AlterField(
            model_name='pointfeature',
            name='featureset',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, to='mapping.FeatureSet'),
        ),
        migrations.AlterField(
            model_name='pointfeature',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to='mapping.FeatureType'),
        ),
        migrations.AlterField(
            model_name='polygonfeature',
            name='featureset',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, to='mapping.FeatureSet'),
        ),
        migrations.AlterField(
            model_name='polygonfeature',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to='mapping.FeatureType'),
        ),
        migrations.AlterField(
            model_name='spatialfeature',
            name='feature_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to='mapping.SpatialFeatureType'),
        ),
        migrations.AlterField(
            model_name='spatialfeaturetype',
            name='display_category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to='mapping.DisplayCategory'),
        ),
    ]