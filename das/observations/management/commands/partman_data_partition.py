import logging

from django.core.management import BaseCommand

from utils.db.postgresql import (
    PSQLExtension,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_data_partition_query,
    vacuum_analyze,
)


class Command(BaseCommand):
    help = """Using pg_partman to run the partition data procedure. It is
    useful for backfilling missing partitions."""

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            type=str,
            help="psql schema to select",
            default="public",
        )
        parser.add_argument(
            "-t",
            "--table",
            type=str,
            help="psql table",
            default="observations_observation",
        )

    def handle(self, *args, **options):

        logger = logging.getLogger(__name__)

        logger.info(f"options: {options}")
        logger.info(f"args: {args}")
        schema = options["schema"]
        table = options["table"]

        if is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            sql_query = partman_data_partition_query(schema=schema, table_name=table)
            logger.info(f"pg_partman is properly installed.")

            try:
                # Data partition
                logger.info(f'running the partition_data_proc with: "{sql_query}"')
                execute_sql_query(query=sql_query, logger=logger, fetch=False)

                # Vacuuming
                vacuum_analyze_sql_query = vacuum_analyze(schema=schema, table_name=table)
                logger.info(f'running the vacuuming with: "{vacuum_analyze_sql_query}"')
                execute_sql_query(query=vacuum_analyze_sql_query, logger=logger, fetch=False)

                self.stdout.write(self.style.SUCCESS("Successfully ran the data partition procedure."))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Could not execute the following query: "{sql_query}". Error: {e}'))
        else:
            self.stdout.write(self.style.WARNING(f"pg_partman is not installed, skipping..."))
