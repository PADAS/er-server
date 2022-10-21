# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2017-02-09 20:06
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import observations.models
import uuid


# def create_default_source_provider(apps, schema_editor):
#     instance, created = observations.models.SourceProvider.objects.get_or_create(
#         id=observations.models.DEFAULT_SOURCE_PROVIDER_ID, name=observations.models.DEFAULT_SOURCE_PROVIDER_KEY,
#     )
#     return instance.id


HYDRATE_SOURCE_PROVIDERS = '''with providers as (select distinct provider_name from observations_source)
      insert into observations_sourceprovider (id, name, created_at, updated_at) select uuid_generate_v4(), provider_name, current_timestamp, current_timestamp from providers where provider_name <> 'default';
      '''

# Update Sources with new SourceProvider reference, based on current
# provider_name value.
SOURCE_PROVIDER_UPDATE = '''with provider as (select id, name from observations_sourceprovider)
                   update observations_source src
                      set provider_id = provider.id
                     from provider
                    where provider.name = src.provider_name;
                    '''

INSERT_DEFAULT_SOURCEPROVIDER = '''
INSERT INTO observations_sourceprovider (created_at, updated_at, id, name) 
                         values (current_timestamp, current_timestamp, '{provider_id}', '{name}')
ON CONFLICT DO NOTHING;
'''.format(provider_id=observations.models.DEFAULT_SOURCE_PROVIDER_ID,
           name=observations.models.DEFAULT_SOURCE_PROVIDER_KEY)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0029_unique_owner_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='SourceProvider',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, null='False',
                                          unique=True, verbose_name='Friendly name for data provider')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RunSQL('SET CONSTRAINTS ALL IMMEDIATE',
                          reverse_sql=migrations.RunSQL.noop),

        migrations.RunSQL(INSERT_DEFAULT_SOURCEPROVIDER,
                          reverse_sql=migrations.RunSQL.noop),

        migrations.RunSQL(sql='create extension IF NOT EXISTS "uuid-ossp";',
                          reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=HYDRATE_SOURCE_PROVIDERS,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.AddField(
            model_name='source',
            name='provider',
            field=models.ForeignKey(default=observations.models.get_default_source_provider_id, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='sources', related_query_name='source', to='observations.SourceProvider'),
        ),
        migrations.RunSQL(sql=SOURCE_PROVIDER_UPDATE,
                          reverse_sql=migrations.RunSQL.noop),
        migrations.AlterUniqueTogether(
            name='source',
            unique_together=set([('provider', 'manufacturer_id')]),
        ),
        migrations.RunSQL(sql=migrations.RunSQL.noop,
                          reverse_sql='SET CONSTRAINTS ALL IMMEDIATE'),
        migrations.RemoveField(
            model_name='source',
            name='provider_name',
        ),

    ]
