import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Protocol

import pytz

from django.db import ProgrammingError, connection


class PARTITION_INTERVALS(Enum):
    ONE_MONTH = "1 month"


class PartitionTableToolProtocol(Protocol):
    def _create_parent_table(self) -> None:
        raise NotImplementedError

    def _set_indexes_constraints_triggers(self) -> None:
        raise NotImplementedError


@dataclass
class IndexData:
    name: str
    columns: List[str]


@dataclass
class ConstraintData:
    name: str
    columns: List[str]


@dataclass
class TriggerData:
    name: str
    sql: str


class PartitionTableTool(PartitionTableToolProtocol):
    logger = logging.getLogger(__name__)

    def __init__(
        self,
        table_name: str,
        partition_column: str,
        partition_start: str,
        interval: str = PARTITION_INTERVALS.ONE_MONTH.value,
    ) -> None:
        self.table_name = table_name
        self.partition_column = partition_column
        self.partition_start = partition_start
        self.interval = interval
        self.partitioned_table_name = f"{table_name}_partitioned"
        self.indexes = None
        self.constraints_unique = None
        self.triggers = None
        self.log_data = {
            "current_step_index": 0,
            "last_migrated_date": None,
            "start_time": None,
        }

    def partition_table(self) -> None:
        self._set_partition_log_data()
        self.logger.warning(f"Partitioning process start at {self.log_data['start_time']}")
        self._pre_requirements_check()
        self._validate_table_partititon_state()

        steps_commands = [
            "_create_parent_table",
            "_partition_setup",
            "_set_indexes_constraints_triggers",
            "_migrate_data_from_table_to_partitioned_table",
            "_drop_indexes_constraints_triggers",
            "_backup_original_table",
            "_set_partitioned_table_as_orginal_table",
            "_create_indexes_constraints_triggers",
            "_migrate_remaining_data",
        ]

        for index in range(self.log_data["current_step_index"], len(steps_commands)):
            getattr(self, steps_commands[index])()

        self.logger.warning(f"Partitioning for {self.table_name} table is completed.")
        self.logger.warning(f"Process takes {(datetime.datetime.now(pytz.utc)) - self.log_data['start_time']}")

    def _pre_requirements_check(self) -> None:
        result = self._execute_sql_command(
            command="SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = 'partman';",
            fetch=True,
        )
        if result and result[0] == 0:
            self.logger.warning("creating partman schema")
            self._execute_sql_command(command="CREATE SCHEMA partman;")

        result = self._execute_sql_command(
            "SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_partman';", fetch=True
        )
        if result and result[0] == 0:
            self.logger.warning("creating pg_partman extension")
            self._execute_sql_command("CREATE EXTENSION pg_partman SCHEMA partman;")

    def _validate_table_partititon_state(self) -> None:
        sql = f"""SELECT COUNT(c.oid)
                FROM pg_class AS c
                WHERE EXISTS (SELECT 1
                            FROM pg_inherits AS i
                            WHERE i.inhrelid = c.oid)
                AND c.relkind IN ('r', 'p')
                AND c.relname LIKE '{self.table_name}%';"""

        result = self._execute_sql_command(command=sql, fetch=True)
        if result and result[0] > 0 and self.log_data["current_step_index"] >= 8:
            self.logger.error(f"{self.table_name} table is already partitioned.")
            exit(1)

    def _set_partition_log_data(self) -> None:
        log_table_name = f"{self.table_name}_partition_log"
        sql_create_log_table = f"""
            CREATE TABLE IF NOT EXISTS {log_table_name}
            (
                id                   INTEGER     DEFAULT 1     NOT NULL PRIMARY KEY,
                current_step_index   INTEGER     DEFAULT 0     NOT NULL,
                last_migrated_date   timestamp WITH TIME ZONE DEFAULT NULL,
                start_time           TIMESTAMP WITH TIME ZONE  NOT NULL
            );
        """
        self._execute_sql_command(command=sql_create_log_table)
        self._execute_sql_command(
            command=f"""
                INSERT INTO {log_table_name} (id, current_step_index, last_migrated_date, start_time)
                VALUES (1, 0, NULL, NOW())
                ON CONFLICT (id) DO NOTHING;
                                 """
        )
        for column in ("current_step_index", "last_migrated_date", "start_time"):
            result = self._execute_sql_command(
                command=f"""
                SELECT {column}
                FROM {log_table_name}
                WHERE id = 1;
            """,
                fetch=True,
            )
            if result[0] and result[0]:
                self.log_data[column] = result[0]
        self.logger.warning(f"Partition log data is set: {self.log_data}")

    def _partition_setup(self) -> None:
        sql = f"""
            SELECT partman.create_parent(
               p_parent_table := 'public.{self.partitioned_table_name}',
               p_control := '{self.partition_column}',
               p_type := 'range',
               p_start_partition := '{self.partition_start}',
               p_interval := '{self.interval}',
               p_default_table := false,
               p_premake := 12
       );
        """
        self._execute_sql_command(command=sql)
        self.logger.warning(f"Partition setup for {self.partitioned_table_name} table is completed.")
        self._set_current_step_index(step=1)

    def _migrate_data_from_table_to_partitioned_table(self) -> None:
        min_value, max_value = self._get_min_max_partition_column()

        batch_size_days = 1
        batch_start = min_value if not self.log_data["last_migrated_date"] else self.log_data["last_migrated_date"]
        batch_end = None

        self.logger.warning(f"Start the migration process from {batch_start} to {max_value}")

        while batch_start < max_value:
            batch_end = batch_start + datetime.timedelta(days=batch_size_days)

            if batch_end > max_value:
                batch_end = max_value

            sql = f"""
                INSERT INTO {self.partitioned_table_name}
                SELECT * FROM {self.table_name}
                WHERE {self.partition_column} >= '{batch_start}'
                AND {self.partition_column} < '{batch_end}'
                ORDER BY {self.partition_column}
                ON CONFLICT DO NOTHING;
            """

            self._execute_sql_command(command=sql)

            batch_start = batch_end

            self._execute_sql_command(command="COMMIT;")
            sql = f"""
                UPDATE {self.table_name}_partition_log
                SET last_migrated_date = '{batch_end}'
                WHERE id = 1;
                COMMIT;
                """
            self._execute_sql_command(command=sql)

        self.logger.warning(f"Data migration for {self.partitioned_table_name} table is completed.")
        self._set_current_step_index(step=3)

    def _drop_indexes_constraints_triggers(self) -> None:
        if self.indexes:
            for index in self.indexes:
                sql = f"""
                    DROP INDEX IF EXISTS {index.name};
                """
                self._execute_sql_command(command=sql)
                self.logger.warning(f"Index: {index.name} dropped successfully.")
        if self.constraints_unique:
            for constraint in self.constraints_unique:
                sql = f"""
                    ALTER TABLE {self.table_name}
                    DROP CONSTRAINT IF EXISTS {constraint.name};
                """
                self._execute_sql_command(command=sql)
                self.logger.warning(f"Constraint: {constraint.name} dropped successfully.")
        if self.triggers:
            for trigger in self.triggers:
                sql = f"""
                    DROP TRIGGER IF EXISTS {trigger.name}
                    ON {self.table_name};
                """
                self._execute_sql_command(command=sql)
                self.logger.warning(f"Trigger: {trigger.name} dropped successfully.")
        self._set_current_step_index(step=4)

    def _backup_original_table(self) -> None:
        self._rename_table(old_name=self.table_name, new_name=f"{self.table_name}_backup")
        self._set_current_step_index(step=5)

    def _set_partitioned_table_as_orginal_table(self) -> None:
        self._rename_table(old_name=self.partitioned_table_name, new_name=self.table_name)
        self._set_current_step_index(step=6)

    def _create_indexes_constraints_triggers(self) -> None:
        if self.indexes:
            for index in self.indexes:
                sql = f"""
                    CREATE INDEX IF NOT EXISTS {index.name}
                    ON {self.table_name}
                    USING btree
                    ({', '.join(index.columns)});
                """
                self._execute_sql_command(command=sql)
                self.logger.warning(f"Index: {index.name} created successfully.")
        if self.constraints_unique:
            for constraint in self.constraints_unique:
                sql = f"""
                    ALTER TABLE {self.table_name}
                    ADD CONSTRAINT {constraint.name}
                    UNIQUE ({', '.join(constraint.columns)});
                """
                self._execute_sql_command(command=sql)
                self.logger.warning(f"Constraint: {constraint.name} created successfully.")
        if self.triggers:
            for trigger in self.triggers:
                self._execute_sql_command(command=trigger.sql)
                self.logger.warning(f"Trigger: {trigger.name} created successfully.")
        self._set_current_step_index(step=7)

    def _migrate_remaining_data(self) -> None:
        sql = f"""
            INSERT INTO {self.table_name}
            SELECT *
            FROM {self.table_name}_backup WHERE recorded_at >= '{self.log_data["start_time"]}'
            ON CONFLICT DO NOTHING;
        """
        self._execute_sql_command(command=sql)
        self.logger.warning(f"Data migration for {self.partitioned_table_name} table is completed.")
        self._set_current_step_index(step=8)

    def _rename_table(self, old_name: str, new_name: str) -> None:
        sql = f"""
            ALTER TABLE {old_name}
            RENAME TO {new_name};
        """
        self._execute_sql_command(command=sql)
        self.logger.warning(f"Old table: {old_name} is renamed to {new_name}.")

    def _get_min_max_partition_column(self):
        sql = f"""
            SELECT MIN({self.partition_column}), MAX({self.partition_column})
            FROM {self.table_name}
            WHERE recorded_at <= '{self.log_data["start_time"]}';
        """
        result = self._execute_sql_command(command=sql, fetch=True)
        return result[0], result[1]

    def _set_current_step_index(self, step: int) -> None:
        self._execute_sql_command(
            command=f"""
                UPDATE {self.table_name}_partition_log
                SET current_step_index = '{step}'
                WHERE id = 1;
            """
        )

    def _execute_sql_command(self, command: str, fetch: bool = False) -> Optional[str]:
        result = None
        with connection.cursor() as cursor:
            try:
                cursor.execute(command)
            except ProgrammingError:
                self.logger.exception("Exiting due to error")
                exit(1)
            if fetch:
                result = cursor.fetchone()
        return result
