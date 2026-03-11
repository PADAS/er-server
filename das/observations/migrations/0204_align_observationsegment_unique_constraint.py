"""State-only migration: align ObservationSegment UniqueConstraint with the DB.

Migration 0200 created the DB constraint as:
    UNIQUE ("start_observation_id", "end_observation_id", "start_recorded_at")

but the Django model only declared (start_observation, end_observation).
Postgres requires the partition key in any unique constraint on a partitioned
table, so the DB was correct all along.  This migration updates Django's state
to match — no DDL is executed.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("observations", "0203_merge_20260224_0642"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="observationsegment",
                    name="observations_observationsegment_unique_segment",
                ),
                migrations.AddConstraint(
                    model_name="observationsegment",
                    constraint=models.UniqueConstraint(
                        fields=["start_recorded_at", "start_observation", "end_observation"],
                        name="observations_observationsegment_unique_segment",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
