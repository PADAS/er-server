import django.db.models.deletion
from django.db import migrations

import core.fields


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0197_update_geofence_schema"),
        ("analyzers", "0059_movementclusteranalyzerconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="subjectanalyzerresult",
            name="event",
            field=core.fields.CompoundTenantForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="analyzer_results",
                to="activity.event",
            ),
        ),
    ]
