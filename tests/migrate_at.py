"""Migrate some data from the AnimalTracking db to the DasDB"""
import os
import sys
DAS_ROOT = '../das'
sys.path.append(os.path.join(os.path.dirname(__file__), DAS_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "das.local_settings")
from django.conf import settings
from django.db import connections
from das.tracker import models

def dictfetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]

def import_animal(chronofile):
    at_conn = connections['animaltracking']
    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from trackingmaster WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)
    animal = rows[0]

    #models.Subject.

    with at_conn.cursor() as at_cursor:
        sql = 'SELECT * from archive_loc WHERE chronofile=%(chronofile)s'
        at_cursor.execute(sql, dict(chronofile=chronofile))
        rows = dictfetchall(at_cursor)

    points = rows


def main():
    import_animal(558)


if __name__ == '__main__':
    main()
