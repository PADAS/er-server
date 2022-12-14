# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-07-23 18:09
from __future__ import unicode_literals

from django.conf import settings
import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import revision.manager
import tagulous.models.fields
import tagulous.models.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mapping', '0010_annotations'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpatialFeatureTypeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True,
                                        serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('slug', models.SlugField()),
                ('count', models.IntegerField(default=0,
                                              help_text='Internal counter of how many times this tag is in use')),
                ('protected', models.BooleanField(default=False,
                                                  help_text='Will not be deleted when the count reaches 0')),
            ],
            options={
                'ordering': ('name',),
                'abstract': False,
            },
            bases=(tagulous.models.models.BaseTagModel, models.Model),
        ),
        migrations.CreateModel(
            name='DisplayCategory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='SpatialFeature',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=50)),
                ('short_name', models.CharField(blank=True, max_length=25)),
                ('external_id', models.CharField(blank=True,
                                                 max_length=100, null=True, unique=True)),
                ('external_source', models.CharField(blank=True, max_length=25)),
                ('attributes', django.contrib.postgres.fields.jsonb.JSONField(default=dict)),
                ('provenance', django.contrib.postgres.fields.jsonb.JSONField(default=dict)),
                ('feature_geometry', django.contrib.gis.db.models.fields.GeometryField(
                    geography=True, srid=4326)),
            ],
            options={
                'abstract': False,
            },
            bases=(revision.manager.RevisionMixin, models.Model),
        ),
        migrations.CreateModel(
            name='SpatialFeatureGroup',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='SpatialFeatureRevision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('object_id', models.UUIDField()),
                ('action', models.CharField(choices=[('added', 'Added'), ('updated', 'Updated'), (
                    'deleted', 'Deleted'), ('rel-del', 'Relation Deleted')], default='added', max_length=10)),
                ('revision_at', models.DateTimeField(auto_now_add=True)),
                ('sequence', models.IntegerField(help_text='Revision sequence')),
                ('data', django.contrib.postgres.fields.jsonb.JSONField(default={})),
                ('user', revision.manager.UserField(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='_spatialfeature_revision', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'default_permissions': (),
            },
        ),
        migrations.CreateModel(
            name='SpatialFeatureType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('attribute_schema',
                 django.contrib.postgres.fields.jsonb.JSONField(default=dict)),
                ('presentation', django.contrib.postgres.fields.jsonb.JSONField(
                    default=dict)),
                ('provenance', django.contrib.postgres.fields.jsonb.JSONField(default=dict)),
                ('external_id', models.CharField(blank=True,
                                                 max_length=100, null=True, unique=True)),
                ('external_source', models.CharField(blank=True, max_length=25)),
                ('display_category', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to='mapping.DisplayCategory')),
                ('tags', tagulous.models.fields.TagField(_set_tag_meta=True,
                                                         help_text='Enter a comma-separated tag string', to='mapping.SpatialFeatureTypeTag')),
            ],
        ),
        migrations.RemoveField(
            model_name='geofeature',
            name='featureset',
        ),
        migrations.RemoveField(
            model_name='geofeature',
            name='type',
        ),
        migrations.RemoveField(
            model_name='linefeature',
            name='attributes',
        ),
        migrations.RemoveField(
            model_name='linefeature',
            name='categorization',
        ),
        migrations.RemoveField(
            model_name='linefeature',
            name='short_name',
        ),
        migrations.RemoveField(
            model_name='pointfeature',
            name='attributes',
        ),
        migrations.RemoveField(
            model_name='pointfeature',
            name='categorization',
        ),
        migrations.RemoveField(
            model_name='pointfeature',
            name='short_name',
        ),
        migrations.RemoveField(
            model_name='polygonfeature',
            name='attributes',
        ),
        migrations.RemoveField(
            model_name='polygonfeature',
            name='categorization',
        ),
        migrations.RemoveField(
            model_name='polygonfeature',
            name='short_name',
        ),
        migrations.AlterField(
            model_name='featuretype',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='linefeature',
            name='fields',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='linefeature',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='pointfeature',
            name='fields',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='pointfeature',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='polygonfeature',
            name='fields',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='polygonfeature',
            name='presentation',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=dict),
        ),
        migrations.CreateModel(
            name='SpatialFeatureGroupQuery',
            fields=[
                ('spatialfeaturegroup_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE,
                                                                 parent_link=True, primary_key=True, serialize=False, to='mapping.SpatialFeatureGroup')),
            ],
            bases=('mapping.spatialfeaturegroup',),
        ),
        migrations.CreateModel(
            name='SpatialFeatureGroupStatic',
            fields=[
                ('spatialfeaturegroup_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE,
                                                                 parent_link=True, primary_key=True, serialize=False, to='mapping.SpatialFeatureGroup')),
            ],
            bases=('mapping.spatialfeaturegroup',),
        ),
        migrations.DeleteModel(
            name='GeoFeature',
        ),
        migrations.AddField(
            model_name='spatialfeature',
            name='feature_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='mapping.SpatialFeatureType'),
        ),
        migrations.AlterUniqueTogether(
            name='spatialfeaturetypetag',
            unique_together=set([('slug',)]),
        ),
        migrations.AlterUniqueTogether(
            name='spatialfeaturerevision',
            unique_together=set([('object_id', 'sequence')]),
        ),
        migrations.AddField(
            model_name='spatialfeaturegroupstatic',
            name='features',
            field=models.ManyToManyField(
                blank=True, related_name='groups', to='mapping.SpatialFeature'),
        ),
    ]
