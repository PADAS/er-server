import logging
from django.core.management.base import BaseCommand
from activity.materialized_view import generate_DDL

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    help = 'Print DDL that is generated to produce event_details_view.'

    def handle(self, *args, **options):

        for line in generate_DDL():
            print(line)
