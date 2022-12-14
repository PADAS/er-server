# Generated by Django 3.1 on 2022-08-12 15:54

from django.db import migrations, models

import django.db.models.deletion
import observations.models


NEW_SUBTYPES = [
                {'display': 'Tourist Vehicle', 'value': 'tourist_vehicle'},
                {'display': 'Excavator', 'value': 'excavator'},
                {'display': 'Maintenance Dump Truck', 'value': 'maintenance_dump_truck'},
                {'display': 'Maintenance Tractor', 'value': 'maintenance_tractor'},
                {'display': 'Van', 'value': 'van'},
                {'display': 'Car', 'value': 'car'},
                ]

SUBJECT_TYPE_VALUE = 'vehicle'


def load_new_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects.using(
        db_alias).get(value=SUBJECT_TYPE_VALUE)
    for subtype in NEW_SUBTYPES:
        defaults = {'display': subtype['display'],
                    'subject_type': subject_type}
        SubjectSubType.objects.using(db_alias).get_or_create(value=subtype['value'],
                                                             defaults=defaults)



class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0125_add_shoebill_subject_subtype'),
    ]

    operations = [
            migrations.RunPython(load_new_subtypes, reverse_code=migrations.RunPython.noop),
    ]
