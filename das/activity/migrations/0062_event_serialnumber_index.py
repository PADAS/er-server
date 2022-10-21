# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-06-19 22:22
from __future__ import unicode_literals

from django.db import migrations

# Create an immutable function for converting bigint to char.
# This is so we're allowed to use it in an index on event table.
create_bigint_to_char_function = '''
create or replace function bigint_to_char(bigint) returns text AS 
$$
select to_char($1, 'FM9999999999999999');
$$  
language sql immutable; 
'''

INDEX_NAME = 'activity_event_bigint_to_char_idx'
index_forward_sql = '''
create index if not exists {index_name} on activity_event (bigint_to_char(serial_number));
'''.format(index_name=INDEX_NAME)

index_reverse_sql = '''
drop index if exists {index_name};
'''.format(index_name=INDEX_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0061_event_permission_cleanup'),
    ]

    operations = [
        migrations.RunSQL(sql='create extension IF NOT EXISTS UNACCENT;',
                          reverse_sql='drop extension if exists UNACCENT;'),

        migrations.RunSQL(sql=create_bigint_to_char_function,
                          reverse_sql='drop function if exists bigint_to_char(bigint);'),

        migrations.RunSQL(sql=index_forward_sql,
                          reverse_sql=index_reverse_sql),
    ]