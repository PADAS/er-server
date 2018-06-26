from __future__ import unicode_literals

import os
import uuid

from django.db import migrations, models
import interval.fields

from core.utils import fetch_sql_migration_files

NEW_UTIL_FUNCTIONS, _ = fetch_sql_migration_files(os.path.dirname(__file__),
                                                  'util/get_cpu_mem.sql',
                                                  None)
OLD_VIEWS, _ = fetch_sql_migration_files(os.path.dirname(__file__), 'util/view.sql', None)
OLD_VIEWS = "{}; {}".format("DROP VIEW stat_v", OLD_VIEWS)
UPDATED_VIEWS, _ = fetch_sql_migration_files(os.path.dirname(__file__),
                                             'util/view_add_cpu_and_mem_07.sql',
                                             None)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0006_add_sql_util'),
    ]

    operations = [
        migrations.CreateModel(
            name='QueryHistory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('pid', models.IntegerField(verbose_name='The OS process id')),
                ('elapsed', interval.fields.IntervalField()),
                ('wait_event', models.CharField(blank=True, max_length=100, null=True)),
                ('cpu_percent', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('mem_percent', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('query', models.TextField(db_index=True)),
                ('digest', models.CharField(db_index=True, max_length=512, verbose_name='The sha1 digest of the query field')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'query histories',
                'verbose_name': 'query history',
            },
        ),
        migrations.AlterIndexTogether(
            name='queryhistory',
            index_together=set([('pid', 'digest', 'updated_at')]),
        ),
        migrations.RunSQL(sql="CREATE EXTENSION IF NOT EXISTS plperlu;",
                          reverse_sql="DROP EXTENSION IF EXISTS plperlu;"),
        migrations.RunSQL(NEW_UTIL_FUNCTIONS,
                          reverse_sql="DROP FUNCTION IF EXISTS get_cpu_mem(int); DROP FUNCTION IF EXISTS get_cpu_mem(text);"),
        migrations.RunSQL(UPDATED_VIEWS, reverse_sql=OLD_VIEWS),
    ]
