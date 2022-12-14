# Generated by Django 2.2.9 on 2021-03-23 14:10

from django.db import migrations


NEW_SUBTYPES = [{"display": "Wild Horse", "value": "wild_horse"},
                {"display": "Tauros", "value": "tauros"},
                {"display": "Red Deer", "value": "red_deer"},
                {"display": "Pelican", "value": "pelican"},
                {"display": "Kulan", "value": "kulan"},
                {"display": "Griffon Vulture", "value": "griffon_vulture"},
                {"display": "Grey Wolf", "value": "grey_wolf"},
                {"display": "Fallow Deer", "value": "fallow_deer"},
                {"display": "European Elk", "value": "european_elk"},
                {"display": "Eurasian Lynx", "value": "eurasian_lynx"},
                {"display": "Eagle Owl", "value": "eagle_owl"},
                {"display": "Demoiselle Crane", "value": "demoiselle_crane"},
                {"display": "Chamois", "value": "chamois"},
                {"display": "Black Vulture", "value": "black_vulture"}]


SUBJECT_TYPE_VALUE = 'wildlife'


def forwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    subject_type_model = apps.get_model('observations', 'SubjectType')
    subject_subtype_model = apps.get_model('observations', 'SubjectSubType')

    subject_type = subject_type_model.objects.using(db_alias).get(value=SUBJECT_TYPE_VALUE)

    for subtype in NEW_SUBTYPES:
        defaults = {'display': subtype['display'],  'subject_type': subject_type}
        subject_subtype_model.objects.using(db_alias).get_or_create(value=subtype['value'],
                                                                    defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0095_update_default_tranform'),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop)
    ]
