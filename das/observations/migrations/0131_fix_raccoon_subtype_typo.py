from django.db import migrations

SUBJECT_TYPE_VALUE = 'wildlife'


def fix_typo_on_raccoon_subtype(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SubjectSubType = apps.get_model('observations', 'SubjectSubType')
    SubjectSubType.objects \
                  .using(db_alias) \
                  .filter(display='Raccoon') \
                  .update(value='raccoon')


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0130_merge_lesser_kudu_male_and_female'),
    ]

    operations = [
        migrations.RunPython(fix_typo_on_raccoon_subtype,
                             reverse_code=migrations.RunPython.noop),
    ]
