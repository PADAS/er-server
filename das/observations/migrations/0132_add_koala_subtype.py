from django.db import migrations

SUBJECT_TYPE_VALUE = 'wildlife'


def load_koala_subtype(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects \
                              .using(db_alias) \
                              .get(value=SUBJECT_TYPE_VALUE)

    defaults = {
        'display': 'Koala',
        'subject_type': subject_type,
    }

    SubjectSubType.objects.using(db_alias).get_or_create(value='koala',
                                                         defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0131_fix_raccoon_subtype_typo'),
    ]

    operations = [
        migrations.RunPython(load_koala_subtype,
                             reverse_code=migrations.RunPython.noop),
    ]
