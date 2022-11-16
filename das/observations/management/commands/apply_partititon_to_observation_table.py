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
from utils.db.postgresql import PSQLExtension, is_postgresql_extension_installed


class PartitionObservationTable(PartitionTableTool):
    def _pre_requirements_check(self) -> None:
        # Call parent pre-requirements check for pg_partman and version
        super()._pre_requirements_check()

        # Ensure btree_gist extension is installed (required for GIST index on recorded_at)
        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.BTREE_GIST, logger=self.logger):
            self.logger.warning("creating btree_gist extension")
            self._execute_sql_command("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    def _create_parent_table(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.partitioned_table_name}
            (
                LIKE {self.original_table_name} INCLUDING DEFAULTS INCLUDING IDENTITY
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
            IndexData(name="observations_observation_created_at_13a1d874", columns=["das_tenant_id", "created_at"]),
            # das_tenant_id index removed - covered by other composite indexes starting with das_tenant_id
            IndexData(
                name="observations_observation_location_id", columns=["das_tenant_id", "location"], index_type="gist"
            ),
            # source_id index removed - covered by unique constraint (das_tenant_id, source_id, recorded_at)
            IndexData(
                name="observations_recorded_at_location_gist",
                columns=["das_tenant_id", "recorded_at", "location"],
                index_type="gist",
            ),
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
                name="trigger_delete_latest_observation_source",
                sql="""
                CREATE OR REPLACE TRIGGER trigger_delete_latest_observation_source
                AFTER DELETE
                ON {table_name}
                FOR EACH ROW
                EXECUTE PROCEDURE delete_latest_observation_source();
                """,
            ),
            TriggerData(
                name="trigger_insert_latest_observation_source",
                sql="""
                CREATE OR REPLACE TRIGGER trigger_insert_latest_observation_source
                AFTER INSERT
                ON {table_name}
                FOR EACH ROW
                EXECUTE PROCEDURE insert_latest_observation_source();
                """,
            ),
            TriggerData(
                name="trigger_update_latest_observation_source",
                sql="""
                CREATE OR REPLACE TRIGGER trigger_update_latest_observation_source
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
