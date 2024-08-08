from django.core.management import BaseCommand

from utils.db.partition import (
    PARTITION_INTERVALS,
    ConstraintData,
    IndexData,
    PartitionTableTool,
    TriggerData,
)


class PartitionObservationTable(PartitionTableTool):

    def _create_parent_table(self) -> None:
        sql = f"""
            CREATE TABLE {self.partitioned_table_name}
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
                        DEFERRABLE INITIALLY DEFERRED,
                PRIMARY KEY (das_tenant_id, {self.partition_column}, id)
                ) PARTITION BY RANGE ({self.partition_column});
            """
        self._execute_sql_command(command=sql)
        self.logger.warning(f"Parent table: {self.partitioned_table_name} created successfully.")
        self._set_current_step_index(step=0)

    def _set_indexes_constraints_triggers(self) -> None:
        self.indexes = [
            IndexData(name="observations_observation_created_at_13a1d874", columns=["created_at"]),
            IndexData(name="observations_observation_das_tenant_id_fa03ec57", columns=["das_tenant_id"]),
            IndexData(name="observations_observation_location_id", columns=["location"]),
            IndexData(name="observations_observation_source_id_813afa19", columns=["source_id"]),
            IndexData(name="observations_recorded_at_location_gist", columns=["recorded_at", "location"]),
        ]

        self.constraints_unique = [
            ConstraintData(
                name="observations_observation_tenant_source_at_unique",
                columns=["das_tenant_id", "source_id", "recorded_at"],
            ),
        ]

        self.triggers = [
            TriggerData(
                name="delete_latest_observation_source",
                sql="""
                CREATE TRIGGER trigger_delete_latest_observation_source
                AFTER DELETE
                ON observations_observation
                FOR EACH ROW
                EXECUTE PROCEDURE delete_latest_observation_source();
                """,
            ),
            TriggerData(
                name="insert_latest_observation_source",
                sql="""
                CREATE TRIGGER trigger_insert_latest_observation_source
                AFTER INSERT
                ON observations_observation
                FOR EACH ROW
                EXECUTE PROCEDURE insert_latest_observation_source();
                """,
            ),
            TriggerData(
                name="update_latest_observation_source",
                sql="""
                CREATE TRIGGER trigger_update_latest_observation_source
                AFTER UPDATE
                ON observations_observation
                FOR EACH ROW
                EXECUTE PROCEDURE update_latest_observation_source();
                """,
            ),
        ]
        self._set_current_step_index(step=2)


class Command(BaseCommand):
    help = "using pg_partman, partition the observations_observation table."

    def handle(self, *args, **options):
        tool = PartitionObservationTable(
            table_name="observations_observation",
            partition_column="recorded_at",
            partition_start="1970-01-01",
            interval=PARTITION_INTERVALS.ONE_MONTH.value,
        )
        tool.partition_table()
