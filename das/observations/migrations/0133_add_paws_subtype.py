from django.db import migrations

SUBJECT_TYPE_VALUE = 'wildlife'


def load_paws_subtype(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    subject_type = SubjectType.objects \
                              .using(db_alias) \
                              .get(value=SUBJECT_TYPE_VALUE)

    defaults = {
        'display': 'Paws',
        'subject_type': subject_type,
    }

    SubjectSubType.objects \
                  .using(db_alias) \
                  .get_or_create(value='paws', defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0132_add_koala_subtype'),
    ]

    operations = [
        migrations.RunPython(load_paws_subtype,
                             reverse_code=migrations.RunPython.noop),
    ]
