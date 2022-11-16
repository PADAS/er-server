from functools import partial

from django.db import migrations

from utils.migrations.defaults import get_default_subject_type, get_subject_type_field

SUBJECT_TYPE_VALUE = "wildlife"


def fix_typo_on_raccoon_subtype(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Subject = apps.get_model("observations", "Subject")
    SubjectType = apps.get_model("observations", "SubjectType")
    SubjectSubType = apps.get_model("observations", "SubjectSubType")

    subject_type = SubjectType.objects.using(db_alias).get(value=SUBJECT_TYPE_VALUE)

    defaults = {"display": "Raccoon", "subject_type": subject_type}
    raccoon, _ = SubjectSubType.objects.using(db_alias).get_or_create(value="raccoon", defaults=defaults)
    broken_subtype = SubjectSubType.objects.using(db_alias).filter(value="racoon").first()

    subject_type_field = get_subject_type_field(SubjectSubType)
    old_default = None

    if subject_type_field:
        old_default = subject_type_field.default
        subject_type_field.default = partial(get_default_subject_type, SubjectType)

    if broken_subtype:
        Subject.objects.using(db_alias).filter(subject_subtype=broken_subtype).update(subject_subtype=raccoon)

        broken_subtype.delete()

    if subject_type_field:
        subject_type_field.default = old_default


class Migration(migrations.Migration):
    dependencies = [
        ("observations", "0130_merge_lesser_kudu_male_and_female"),
    ]

    operations = [
        migrations.RunPython(fix_typo_on_raccoon_subtype, reverse_code=migrations.RunPython.noop),
    ]
