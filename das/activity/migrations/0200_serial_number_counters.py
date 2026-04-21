import uuid

import django.db.models.deletion
from django.db import migrations, models

import utils.migrations.columns


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_token"),
        ("activity", "0199_performance_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventSerialNumberCounter",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("last_value", models.BigIntegerField(default=0)),
                (
                    "das_tenant",
                    models.ForeignKey(
                        default=utils.migrations.columns.default_tenant_id,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.dastenant",
                    ),
                ),
            ],
            options={
                "db_table": "activity_eventserialnumbercounter",
                "base_manager_name": "objects",
                "default_manager_name": "objects",
            },
        ),
        migrations.AddConstraint(
            model_name="eventserialnumbercounter",
            constraint=models.UniqueConstraint(
                fields=("das_tenant",),
                name="activity_eventserialnumbercounter_tenant_unique",
            ),
        ),
        migrations.CreateModel(
            name="PatrolSerialNumberCounter",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("last_value", models.BigIntegerField(default=0)),
                (
                    "das_tenant",
                    models.ForeignKey(
                        default=utils.migrations.columns.default_tenant_id,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.dastenant",
                    ),
                ),
            ],
            options={
                "db_table": "activity_patrolserialnumbercounter",
                "base_manager_name": "objects",
                "default_manager_name": "objects",
            },
        ),
        migrations.AddConstraint(
            model_name="patrolserialnumbercounter",
            constraint=models.UniqueConstraint(
                fields=("das_tenant",),
                name="activity_patrolserialnumbercounter_tenant_unique",
            ),
        ),
    ]
