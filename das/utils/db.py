import time
from django.db import connection
from django.db.utils import InterfaceError, OperationalError, DataError, IntegrityError, ProgrammingError
from collections import namedtuple
from django.db.models import Lookup
from django.db.models.fields import Field

CONNECTION_EXCEPTIONS = (InterfaceError, OperationalError)
DATABASE_OPERATIONS_EXCEPTIONS = (DataError, IntegrityError, ProgrammingError)


class NotEqual(Lookup):
    lookup_name = 'ne'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return '%s <> %s' % (lhs, rhs), params


Field.register_lookup(NotEqual)


def extract_sql_and_params_from_queryset(queryset):
    #
    # Note this method returns a tuple not a scalar string. The first element is the query and the second is/are the
    # input parameter(s) to substitute for place holders in the returned query.
    #
    return queryset.query.get_compiler(queryset.db).as_sql()


def extract_sql_from_queryset(queryset):
    #
    # This method returns a scalar string representing the query after parameter binding, so what it returns is readily
    # executable without any further tinkering.
    #
    sql, params = extract_sql_and_params_from_queryset(queryset)
    with connection.cursor() as cursor:
        return cursor.mogrify(sql, params).decode('utf-8')


def log_queryset_execution_plan(queryset, logger, include_query=False):
    #
    # Given a queryset and a logger, this method would write the query execution plan to the log file
    #
    query_plans = list()
    sql, params = extract_sql_and_params_from_queryset(queryset)

    with connection.cursor() as cursor:
        if include_query:
            logger.info("Query: {}".format(cursor.mogrify(sql, params)))

        cursor.execute("EXPLAIN {}".format(sql, params))
        query_plans = cursor.fetchall()

    for qp in query_plans:
        logger.info(qp)


def pause_and_close_current_connection(db_connection, logger, pause_seconds=30):
    logger.error("DB connection error. Pause {} seconds before retry.".format(pause_seconds))
    time.sleep(pause_seconds)
    db_connection.close()


def fetchall(cursor):
    """Return all rows from a cursor as a namedtuple"""
    desc = cursor.description
    nt_result = namedtuple('NamedRow', [col[0] for col in desc])
    return [nt_result(*row) for row in cursor.fetchall()]


def fetchone(cursor):
    """Return all rows from a cursor as a namedtuple"""
    desc = cursor.description
    nt_result = namedtuple('NamedRow', [col[0] for col in desc])
    row = cursor.fetchone()
    if row:
        return nt_result(*row)
    else:
        return None
