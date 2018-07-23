import logging
from django.core.management.base import BaseCommand
from core import query_monitor
from django.db import connection
import utils.db

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    This is the command-line interface to kickoff monitoring of long running queries for performance debugging purposes.
    All discovered queries passing all the input criteria described below are saved to the core_QueryMonitor table that
    the user can query and filter as needed. And, when these historical records are no longer deemed useful, they can be
    selectively deleted or the entire history table be truncated as well without any ill effects to the tool.
    Input parameters:
        --interval <number of seconds between calls to snapshot running queries (in seconds)>
            Depending on the desired elapsed_threshold below, one would typically set interval to be a little bit
            shorter then the elapsed_threshold. For instance, to monitor for queries that run longer than 300 seconds
            (5 minutes), a reasonable value for interval would be 4 minutes (240 seconds)
        --elapsed_threshold <Minimum query elapsed time to save to query history>
            The minimum query elapsed time to log. Skylight database has a frequent rate of updates, so to log every
            queries to history would blow up query history very quickly. Also, queries takes very short time to execute
            are generally not of interest. Therefore, a user can use this parameter to log to history only queries that
            take a considerable amount of time to execute.
        --purge_history
            The presence of this parameter will have this tool truncate the core_QueryHistory table before it starts a
            new round of history collecting.
        --query_filter <Text phrase to match running queries with (case-insensitive)>
            In specific cases, a user may want to log only a certain types of queries. For instance, if one wants to
            only log all VACCUM queries, then this parameter can be used for this specific purpose (e.g., --query_filter
            vacuum). Note the value entered for this parameter will be treated as case-insensitive for convenience.
            Also, a filter phrase with space(s) can be entered with double-quotes around the entire phrase, for example:
                --query_filter "from observations_route"
        --invert_query_filter <Text phrase to exclude running queries with (case-insensitive)>
            In other cases, a user may want to specifically exclude a certain types of queries from history. For
            instance, if one wants to log all queries matching above criteria but not any VACCUM queries, then this
            parameter can be used for this specific purpose (e.g., --invert_query_filter vacuum). Note the value entered
            for this parameter will be treated as case-insensitive for convenience. Also, a filter phrase with space(s)
            can be entered with double-quotes around the entire phrase, for example:
                --query_filter "vacuum analyze observations_observationstaging"
    Output:
    All useful output from this tool is written to the core_QueryHistory table. So, while this tool is running, one
    would typically access the data in the history table in another terminal concurrently.
    Usages:
    This command is provided to afford the user the most flexible way to configure the query monitoring process during
    debugging sessions. For ongoing collecting of long running queries that take more than 5 minutes, there's already a
    celery task to address that need. Below are some example usages for this tool:
        o During backfill operation, sometimes specific API calls take longer to return than normal:
            For this usage, one may want to start this tool with this set of parameters:
                python manage.py monitor_database_query
                    --interval 60
                    --elapsed_threshold 120
                    --query_filter <some unique part of the specific API calls interested in>
        o For actively updated tables, if one wants to know if vacuums are scheduled frequently enough to keep
          fragmentation in check, one may want to start this tool with this set of parameters:
                python manage.py monitor_database_query
                    --interval 15
                    --elapsed_threshold 30
                    --query_filter vacuum
        o Inversely, if a user want to log all long running queries excluding vacuum operations, which can be very
          useful to avoid clutter, one may want to start this tool with this set of parameters
                python manage.py monitor_database_query
                    --interval 15
                    --elapsed_threshold 30
                    --invert_query_filter vacuum
    """
    help = 'Monitor and log database queries...'

    def add_arguments(self, parser):
        parser.add_argument('--interval', default=240, dest='interval',
                            help='Interval between calls to snapshot running queries (in seconds)')
        parser.add_argument('--elapsed_threshold', default=300, dest='elapsed_threshold',
                            help='Minimum query elapsed time to save to query history')
        parser.add_argument('--purge_history', default=False, dest='purge_history', action='store_true',
                            help='When the tool starts should it purge old query history or not')
        parser.add_argument('--query_filter', default=None, dest='query_filter',
                            help='Text phrase to match running queries with')
        parser.add_argument('--invert_query_filter', default=None, dest='invert_query_filter',
                            help='Text phrase to exclude running queries with')

    def handle(self, *args, **options):
        while True:
            try:
                query_monitor.configure_query_monitor(int(options['interval']),
                                                      int(options['elapsed_threshold']),
                                                      options['purge_history'],
                                                      options['query_filter'],
                                                      options['invert_query_filter'])
                break
            except utils.db.CONNECTION_EXCEPTIONS as ce:
                utils.db.pause_and_close_current_connection(connection, logger)
