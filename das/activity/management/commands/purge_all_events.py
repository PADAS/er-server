from django.core.management.base import BaseCommand

import logging
logger = logging.getLogger(__name__)

from activity.models import Event
from django.db import connections

RESET_SERIAL_NUMBER_SQL = "select setval('public.activity_event_serial_number_seq', 1, false);"

REVISION_DELETIONS = [
    'delete from activity_eventrevision',
    'delete from activity_eventattachementrevision',
    'delete from activity_eventdetailsrevision',
    'delete from activity_eventfilerevision',
    'delete from activity_eventnoterevision',
    'delete from activity_eventphotorevision',
]


def delete_extra_data():
    with connections['default'].cursor() as cursor:

        for sql in REVISION_DELETIONS:
            print('\nExecuting: {}\n'.format(sql,))
            cursor.execute(sql)


def reset_serial_number():
    print('\nResetting serial_number sequence to next-value=1\n.')
    with connections['default'].cursor() as cursor:
        cursor.execute(RESET_SERIAL_NUMBER_SQL)


class Command(BaseCommand):

    help = 'Purge events from a system.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--i-really-mean-it',
            action='store',
            dest='i-really-mean-it',
            default='no',
            help='A required flag, to help avoid accidentally running this command.',
        )

    def handle(self, *args, **options):

        i_really_mean_it = options['i-really-mean-it']

        if i_really_mean_it == 'yes':
            print('\nDeleting all events.\n')
            result = Event.objects.all().delete()
            print('\nResult: {}\n'.format(result))
            reset_serial_number()

            delete_extra_data()

        else:
            print('\nStubbornly refusing to delete events.\n')
