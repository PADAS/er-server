from django.db import migrations

SUBJECT_TYPE_VALUE = 'wildlife'


def fix_typo_on_raccoon_subtype(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Subject = apps.get_model('observations', 'Subject')
    SubjectType = apps.get_model('observations', 'SubjectType')
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')

    subject_type = SubjectType.objects \
                              .using(db_alias) \
                              .get(value=SUBJECT_TYPE_VALUE)

    defaults = {'display': 'Raccoon', 'subject_type': subject_type}
    raccoon, _ = SubjectSubType.objects \
                               .using(db_alias) \
                               .get_or_create(value='raccoon', defaults=defaults)
    broken_subtype = SubjectSubType.objects \
                                   .using(db_alias) \
                                   .filter(value='racoon') \
                                   .first()

    if broken_subtype:
        Subject.objects \
               .using(db_alias) \
               .filter(subject_subtype=broken_subtype) \
               .update(subject_subtype=raccoon)

        broken_subtype.delete()


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0130_merge_lesser_kudu_male_and_female'),
    ]

    operations = [
        migrations.RunPython(fix_typo_on_raccoon_subtype,
                             reverse_code=migrations.RunPython.noop),
    ]
