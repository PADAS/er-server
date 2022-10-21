from django.db import migrations

NEW_SUBTYPES = [{'display': 'Lesser Kudu', 'value': 'lesser_kudu'}]
OLD_SUBTYPES = ['lesser_kudu-female', 'lesser_kudu-male']

SUBJECT_TYPE_VALUE = 'wildlife'


def load_lesser_kudu_subtype(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects.using(
        db_alias).get(value=SUBJECT_TYPE_VALUE)

    for subtype in NEW_SUBTYPES:
        defaults = {'display': 'Lesser Kudu',
                    'subject_type': subject_type}
        SubjectSubType.objects.using(db_alias).get_or_create(value='lesser_kudu',
                                                             defaults=defaults)


def remove_lesser_kudu_gender_subtypes(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')

    for subtype in OLD_SUBTYPES:
        SubjectSubType.objects.using(db_alias).filter(value=subtype).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0129_add_lesser_kudu_subtype'),
    ]

    operations = [
        migrations.RunPython(remove_lesser_kudu_gender_subtypes,
                             reverse_code=migrations.RunPython.noop),
        migrations.RunPython(load_lesser_kudu_subtype,
                             reverse_code=migrations.RunPython.noop),
    ]
