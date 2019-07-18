import time
import functools

from utils.middleware import request_data

from datadog import statsd

from psycopg2.extensions import cursor
from django.contrib.gis.db.backends.postgis.base import (
    DatabaseWrapper as DjangoDatabaseWrapper
)


class _cursor_wrapper:
    '''
    A thin wrapper around psycopg2 cursor, to allow us to capture time for queries.
    '''
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, args=None):
        start = time.time()
        verb = query[:query.find(' ')]
        if hasattr(request_data, 'view_name'):
            view_name = request_data.view_name
        else:
            view_name = 'na'

        result = self.cursor.execute(query, args)
        end = time.time()
        statsd.histogram('das.query_time', end - start,
                         tags=[
                             f'verb:{verb}',
                             f'view:{view_name}'
                         ]
                         )
        return result


    # def executemany(self, query, args):
    #     return self.cursor.executemany(query, args)

    def __getattr__(self, attr):
        return getattr(self.cursor, attr)

    def __iter__(self):
        return iter(self.cursor)


class DatabaseWrapper(DjangoDatabaseWrapper):
    def create_cursor(self, name=None):
        return _cursor_wrapper(self.connection.cursor())
