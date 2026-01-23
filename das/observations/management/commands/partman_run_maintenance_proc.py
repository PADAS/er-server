"""
Django management command to run `partman.run_maintenance_proc()` (pg_partman 5.x).

This is the preferred maintenance entrypoint for PG11+ since it can commit
between partition sets and reduces lock contention compared to the legacy
`run_maintenance()` function.
"""

import logging

from django.core.management import BaseCommand

from utils.db.postgresql import (
    FetchType,
    PSQLExtension,
    execute_sql_query,
    is_postgresql_extension_installed,
    partman_partition_maintenance_proc_query,
)


class Command(BaseCommand):
    help = "Run pg_partman maintenance procedure (run_maintenance_proc)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--wait",
            type=int,
            default=0,
            help="Seconds to wait between partition set maintenance runs (p_wait).",
        )
        parser.add_argument(
            "--analyze",
            type=str,
            choices=["null", "true", "false"],
            default="null",
            help="Whether to ANALYZE after creating child tables (p_analyze). Use null to keep pg_partman default.",
        )
        parser.add_argument(
            "--no-jobmon",
            action="store_true",
            default=False,
            help="Disable pg_jobmon usage (p_jobmon). By default, pg_partman's default (enabled) is used.",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Enable debug notices (p_debug).",
        )

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        logger.info(f"options: {options}")
        logger.info(f"args: {args}")

        if not is_postgresql_extension_installed(psql_extension=PSQLExtension.PG_PARTMAN, logger=logger):
            self.stdout.write(self.style.WARNING("pg_partman is not installed, skipping..."))
            return

        analyze_str = options["analyze"]
        analyze = None
        if analyze_str == "true":
            analyze = True
        elif analyze_str == "false":
            analyze = False

        # Only pass jobmon/debug if explicitly specified to maximize version compatibility
        jobmon = False if options["no_jobmon"] else None
        debug = True if options["debug"] else None

        sql_query = partman_partition_maintenance_proc_query(
            wait=options["wait"],
            analyze=analyze,
            jobmon=jobmon,
            debug=debug,
        )
        logger.info(f'running pg_partman maintenance proc with: "{sql_query}"')
        execute_sql_query(query=sql_query, logger=logger, fetch_type=FetchType.NONE)
        self.stdout.write(self.style.SUCCESS("Successfully ran pg_partman maintenance procedure."))
