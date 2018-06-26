# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from django.db import migrations

util_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'sql', 'util'))

util_files = ['aggregate.sql',
              'get_current_timeofday.sql',
              'get_foreign_key_cmd_by_db_owner.sql',
              'get_primary_key_columns.sql',
              'get_primary_key_where_clause.sql',
              'get_table_column.sql',
              'get_table_column_and_type.sql',
              'get_table_foreign_key.sql',
              'get_table_index.sql',
              'get_update_table_columns.sql',
              'get_update_where_clause.sql',
              'is_schema_exists.sql',
              'update_sequence.sql',
              'update_all_sequence.sql',
              'export_data.sql',
              'view.sql'
              ]

SQL_COMMANDS = ""
for util in util_files:
    with open(os.path.join(util_dir, util)) as file:
        SQL_COMMANDS += "\n" + file.read()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_auto_20161007_1303'),
    ]

    operations = [
        migrations.RunSQL(SQL_COMMANDS, "SELECT 1;"),
    ]
