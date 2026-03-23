"""State-only migration: align ObservationSegment UniqueConstraint and model state with the DB.

1) UniqueConstraint: Migration 0200 created the DB constraint as
   UNIQUE ("start_observation_id", "end_observation_id", "start_recorded_at").
   The Django model only declared (start_observation, end_observation).
   Postgres requires the partition key in any unique constraint on a partitioned
   table, so the DB was correct all along. This updates Django's state to match.

2) Indexes, BitField, Meta: 0200 created the table via raw SQL and used
   SeparateDatabaseAndState for CreateModel, so the migration state never got
   the Meta indexes, ordering, custom manager, or BitField type for exclusion_flags.
   This updates state only; no DDL is executed.
"""

import bitfield.models
import django.contrib.gis.db.models as gis_models
from django.db import migrations, models

import observations.models


class Migration(migrations.Migration):

    dependencies = [
        ("observations", "0203_merge_20260224_0642"),
    ]

    operations = [
        # 1) Align UniqueConstraint state with DB.
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
        # 2) Align Meta.indexes, BitField, field options, ordering, manager (state only).
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="observationsegment",
                    index=models.Index(
                        fields=["das_tenant", "subject", "start_recorded_at"],
                        name="observation_das_ten_844e39_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="observationsegment",
                    index=models.Index(
                        fields=["das_tenant", "subject", "end_recorded_at"],
                        name="observation_das_ten_ff294d_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="observationsegment",
                    index=models.Index(
                        fields=["start_observation", "end_observation"],
                        name="observation_start_o_68bbbe_idx",
                    ),
                ),
                migrations.AddIndex(
                    model_name="observationsegment",
                    index=models.Index(
                        fields=["das_tenant", "subject", "exclusion_flags"],
                        name="observation_das_ten_aee6b0_idx",
                    ),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="exclusion_flags",
                    field=bitfield.models.BitField(
                        default=0,
                        flags=[
                            ("EXCLUDED_MANUALLY", "EXCLUDED_MANUALLY"),
                            ("EXCLUDED_AUTOMATICALLY", "EXCLUDED_AUTOMATICALLY"),
                        ],
                    ),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="distance_meters",
                    field=models.FloatField(help_text="Distance in meters between observations (ST_Distance)"),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="end_recorded_at",
                    field=models.DateTimeField(
                        db_index=True,
                        help_text="End observation recorded_at (denormalized)",
                    ),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="geometry",
                    field=gis_models.LineStringField(
                        help_text="LineString geometry from start to end observation",
                        srid=4326,
                    ),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="speed_kmh",
                    field=models.FloatField(help_text="Speed in km/h between observations"),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="start_recorded_at",
                    field=models.DateTimeField(
                        db_index=True,
                        help_text="Start observation recorded_at (denormalized)",
                    ),
                ),
                migrations.AlterField(
                    model_name="observationsegment",
                    name="time_gap_ms",
                    field=models.FloatField(help_text="Time gap in milliseconds between observations"),
                ),
                migrations.AlterModelOptions(
                    name="observationsegment",
                    options={"ordering": ["start_recorded_at"]},
                ),
                migrations.AlterModelManagers(
                    name="observationsegment",
                    managers=[
                        ("objects", observations.models.ObservationSegmentManager()),
                    ],
                ),
            ],
            database_operations=[],
        ),
    ]
