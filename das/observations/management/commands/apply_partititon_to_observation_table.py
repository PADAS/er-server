from django.core.management import BaseCommand

from utils.db.partition import (
    PARTITION_INTERVALS,
    ConstraintData,
    ForeignKeyData,
    IndexData,
    PartitionTableTool,
    TableData,
    TriggerData,
)


class PartitionObservationTable(PartitionTableTool):

    def _create_parent_table(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.partitioned_table_name}
            (
                id              uuid                     NOT NULL,
                location        geometry(Point, 4326)    NOT NULL,
                recorded_at     timestamp WITH TIME ZONE NOT NULL,
                created_at      timestamp WITH TIME ZONE NOT NULL,
                additional      jsonb,
                source_id       uuid                     NOT NULL,
                exclusion_flags bigint                   NOT NULL,
                das_tenant_id   uuid                     NOT NULL
                    CONSTRAINT observations_observa_das_tenant_id_fa03ec57_fk_core_dast
                        REFERENCES core_dastenant
                        DEFERRABLE INITIALLY DEFERRED
            ) PARTITION BY RANGE ({self.partition_column});
            """
        self._execute_sql_command(command=sql)
        self._set_current_step(step=1)
        self.logger.warning(f"Parent table: {self.partitioned_table_name} created successfully.")


class Command(BaseCommand):
    help = "using pg_partman, partition the observations_observation table."

    def add_arguments(self, parser):
        parser.add_argument(
            "-r",
            "--rollback",
            dest="rollback",
            action="store",
            default=False,
            help="Rollback the partitioning of the table.",
        )

    def handle(self, *args, **options):
        should_rollback = bool(options["rollback"])

        self.stdout.write(self.style.SUCCESS(f"Running in [{'rollback' if should_rollback else 'normal'}] mode."))

        indexes = [
            IndexData(name="observations_observation_created_at_13a1d874", columns=["created_at"]),
            IndexData(name="observations_observation_das_tenant_id_fa03ec57", columns=["das_tenant_id"]),
            IndexData(name="observations_observation_location_id", columns=["location"]),
            IndexData(name="observations_observation_source_id_813afa19", columns=["source_id"]),
            IndexData(name="observations_recorded_at_location_gist", columns=["recorded_at", "location"]),
        ]

        unique_constraints = [
            ConstraintData(
                name="tenant_source_at_unique",
                columns=["das_tenant_id", "source_id", "recorded_at"],
            ),
        ]

        foreign_keys = [
            ForeignKeyData(
                name="observations_observa_das_tenant_id_fa03ec57_fk_core_dast",
                foreign_column="das_tenant_id",
                references="core_dastenant",
            )
        ]

        triggers = [
            TriggerData(
                name="delete_latest_observation_source",
                sql="""
                CREATE TRIGGER trigger_delete_latest_observation_source
                AFTER DELETE
                ON {table_name}
                FOR EACH ROW
                EXECUTE PROCEDURE delete_latest_observation_source();
                """,
            ),
            TriggerData(
                name="insert_latest_observation_source",
                sql="""
                CREATE TRIGGER trigger_insert_latest_observation_source
                AFTER INSERT
                ON {table_name}
                FOR EACH ROW
                EXECUTE PROCEDURE insert_latest_observation_source();
                """,
            ),
            TriggerData(
                name="update_latest_observation_source",
                sql="""
                CREATE TRIGGER trigger_update_latest_observation_source
                AFTER UPDATE
                ON {table_name}
                FOR EACH ROW
                EXECUTE PROCEDURE update_latest_observation_source();
                """,
            ),
        ]

        table_data = TableData(
            primary_key_columns=["das_tenant_id", "id"],
            indexes=indexes,
            unique_constraints=unique_constraints,
            foreign_keys=foreign_keys,
            triggers=triggers,
        )
        if not should_rollback:
            table_data.primary_key_columns.append("recorded_at")

        tool = PartitionObservationTable(
            original_table_name="observations_observation",
            partition_column="recorded_at",
            partition_interval=PARTITION_INTERVALS.MONTHLY.value,
            table_data=table_data,
            migrate_batch_size_per_interval=10000,
        )
        if not should_rollback:
            self.stdout.write(self.style.SUCCESS("Starting partitioning process."))
            tool.partition_table()
        else:
            self.stdout.write(self.style.SUCCESS("Starting rollback process."))
            tool.rollback()
        self.stdout.write(self.style.SUCCESS(f"Process [{'rollback' if should_rollback else 'partition'}] finish."))
