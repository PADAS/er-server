import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Max

from utils.migrations.columns import default_tenant_id


def populate_counters(apps, schema_editor):
    """Seed SerialNumberCounter rows from existing per-tenant max(serial_number)."""
    SerialNumberCounter = apps.get_model("core", "SerialNumberCounter")
    Event = apps.get_model("activity", "Event")
    Patrol = apps.get_model("activity", "Patrol")
    db_alias = schema_editor.connection.alias

    for Model, label in ((Event, "activity.Event"), (Patrol, "activity.Patrol")):
        tenant_maxes = (
            Model.objects.using(db_alias)
            .filter(serial_number__isnull=False)
            .values("das_tenant_id")
            .annotate(max_sn=Max("serial_number"))
        )
        counters = [
            SerialNumberCounter(
                das_tenant_id=row["das_tenant_id"],
                model_name=label,
                last_value=row["max_sn"],
            )
            for row in tenant_maxes
        ]
        if counters:
            SerialNumberCounter.objects.using(db_alias).bulk_create(counters)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_token"),
        ("activity", "0199_performance_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="SerialNumberCounter",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("model_name", models.CharField(max_length=255)),
                ("last_value", models.BigIntegerField(default=0)),
                (
                    "das_tenant",
                    models.ForeignKey(
                        default=default_tenant_id,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.dastenant",
                    ),
                ),
            ],
            options={
                "base_manager_name": "objects",
                "default_manager_name": "objects",
            },
        ),
        migrations.AddConstraint(
            model_name="serialnumbercounter",
            constraint=models.UniqueConstraint(
                fields=("das_tenant", "model_name"),
                name="core_serialnumbercounter_tenant_model_unique",
            ),
        ),
        migrations.RunPython(
            code=populate_counters,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
