from django.db import migrations

from observations.migration_utils import TenantSubjectSubTypeLoader

vehicle_subtype_loader = (
    TenantSubjectSubTypeLoader(subject_type_value="vehicle")
    .add_subject_subtype(display="Water Bowser", value="water_bowser")
    .add_subject_subtype(display="School Bus", value="school_bus")
    .add_subject_subtype(display="10 Wheeler", value="ten_wheeler")
    .add_subject_subtype(display="Jimny", value="jimny")
)


class Migration(migrations.Migration):
    dependencies = [
        ("observations", "0207_django_42"),
    ]

    operations = [
        migrations.RunPython(
            code=vehicle_subtype_loader.load,
            reverse_code=migrations.RunPython.noop,
        )
    ]
