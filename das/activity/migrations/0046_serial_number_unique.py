# -*- coding: utf-8 -*-
# Generated by Django 1.9.10 on 2016-12-01 17:47
from __future__ import unicode_literals
from django.db import migrations, models
from django.conf import settings

# current DB owner for default db, needed for multiple platforms/databases
db = getattr(settings, 'DATABASES', {})
db_user = db['default']['USER'] if 'default' in db else 'postgres'
# and because Azure requires the host name to be prepended, we need to
# strip off anything with an '@' in it
if '@' in db_user:
    parts = db_user.split('@')
    db_user = parts[0]

class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0045_serial_number'),
    ]

    operations = [
        migrations.RunSQL(
            sql='''with generated as (select id, row_number() over (order by created_at) as rnum from activity_event)
               update activity_event ae
                  set serial_number = generated.rnum
                 from generated
                where ae.id = generated.id;
                ''',
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            sql='''CREATE SEQUENCE public.activity_event_serial_number_seq
                      INCREMENT 1
                      MINVALUE 1
                      MAXVALUE 9223372036854775807
                      START 1
                      CACHE 1;
                    ALTER TABLE public.activity_event_serial_number_seq
                      OWNER TO {};'''.format(db_user),
            reverse_sql='''drop sequence activity_event_serial_number_seq ;'''
        ),
        migrations.RunSQL(
            sql="select setval('public.activity_event_serial_number_seq', (select max(serial_number) from activity_event), true);",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            sql="alter table activity_event alter column serial_number set default nextval('activity_event_serial_number_seq'::regclass);",
            reverse_sql="alter table activity_event alter COLUMN serial_number drop default;"
        ),
        # migrations.AlterField(
        #     model_name='event',
        #     name='serial_number',
        #     field=models.BigIntegerField(unique=True, verbose_name='Serial Number'),
        # ),
        migrations.AddField(
            model_name='event',
            name='end_time',
            field=models.DateTimeField(null=True, verbose_name='End Time'),
        ),
        migrations.AlterField(
            model_name='event',
            name='serial_number',
            field=models.BigIntegerField(
                blank=True, null=True, unique=True, verbose_name='Serial Number'),
        ),

    ]
