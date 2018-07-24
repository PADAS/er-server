import logging
import sys
import time

from django.db import connection

from core.utils import message_digest
import utils.db

logger = logging.getLogger(__name__)

SHORTEST_MONITORING_INTERVAL = 30
EXECUTE_ONCE_INTERVAL = 0
DEFAULT_ELAPSED_THRESHOLD_IN_SECS = 240

PURGE_HISTORY_STMT = 'TRUNCATE TABLE core_queryhistory;'


def configure_query_monitor(interval=SHORTEST_MONITORING_INTERVAL,
                        elapsed_threshold=DEFAULT_ELAPSED_THRESHOLD_IN_SECS,
                        purge_history=False,
                        query_filter=None,
                        invert_query_filter=None):
    logger.info('Starting query monitor')

    # query to fetch currently running queries
    fetch_running_queries_stmt = "SELECT s.* FROM stat_v s WHERE s.elapsed >= '%s seconds'"

    query_params = [elapsed_threshold]

    if query_filter is not None:
        fetch_running_queries_stmt += " AND query ~* %s"
        query_params.append(query_filter)

    if invert_query_filter is not None:
        fetch_running_queries_stmt += " AND query !~* %s"
        query_params.append(invert_query_filter)

    # query to check if a currently running query is already present in the query history
    lookup_query_in_history_stmt = \
        "SELECT id FROM core_queryhistory WHERE pid=%s AND digest=%s AND updated_at > (now() - %s) ORDER BY updated_at"

    # query to insert into the QueryHistory table
    insert_into_history_stmt = \
        "INSERT INTO core_queryhistory" \
        "(id, pid, elapsed, wait_event, cpu_percent, mem_percent, query, digest, created_at, updated_at)"\
        "VALUES(uuid_generate_v4(), %s, %s, %s, %s, %s, %s, %s, now(), now())"

    # query to insert/u[pdate running query is already present in the query history
    update_history_stmt = \
        "UPDATE core_queryhistory " \
        "SET elapsed = %s, wait_event = %s, cpu_percent = %s, mem_percent = %s, updated_at = now()" \
        "WHERE id = %s"

    # if we were requested to first purge query history, we do so before starting the loop to save new ones to history
    if purge_history:
        with connection.cursor() as cursor:
            cursor.execute(PURGE_HISTORY_STMT)

    # main loop to fetch and save running queries to the query history
    while True:
        try:
            with connection.cursor() as cursor:
                cursor.execute(fetch_running_queries_stmt, query_params)
                queries = utils.db.fetchall(cursor)

                for query in queries:
                    query_digest = message_digest(query.query)
                    cursor.execute(lookup_query_in_history_stmt, [query.pid, query_digest, query.elapsed])
                    hist = utils.db.fetchone(cursor)
                    if hist is None:
                        cursor.execute(insert_into_history_stmt,
                                       [query.pid,
                                        query.elapsed,
                                        query.wait_event,
                                        query.cpu_percent,
                                        query.mem_percent,
                                        query.query,
                                        query_digest])
                    else:
                        cursor.execute(update_history_stmt,
                                       [query.elapsed,
                                        query.wait_event,
                                        query.cpu_percent,
                                        query.mem_percent,
                                        hist.id])

            # if given interval is zero, then caller intend to execute this code only once, so we exit silently
            if interval == 0:
                break

            time.sleep(interval)
        except KeyboardInterrupt:
            sys.exit(0)
        except utils.db.CONNECTION_EXCEPTIONS as ce:
            # If we get here, the connection to the db server had been severed, we wait and a bit and try again
            utils.db.pause_and_close_current_connection(connection, logger)
        except utils.db.DATABASE_OPERATIONS_EXCEPTIONS as de:
            error = "Database Error: {0}".format(de).replace("\n", " ")
            logger.error("%s", error)
        except Exception as e:
            error = "{0}".format(e).replace("\n", " ")
            logger.error("%s", error)
