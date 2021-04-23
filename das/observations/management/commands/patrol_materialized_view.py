import logging
import pprint
from django.core.management.base import BaseCommand
from observations.materialized_views import patrols_view


class Command(BaseCommand):
    help = 'Patrol materialized view Commands'

    def handle(self, *args, **options):
        if options['print_ddl']:
            print(f"{patrols_view.generate_ddl}")
        if options['refresh_view']:
            patrols_view.refresh_view()
        if options['drop_view']:
            patrols_view.drop_view()
        if options['recreate_view']:
            patrols_view.drop_view()
            patrols_view.refresh_view()

    def add_arguments(self, parser):
        parser.add_argument('-p', '--print-ddl',  action='store_true',
                            help='print DDL used to produce patrol_view table')
        parser.add_argument('-r', '--refresh-view',  action='store_true',
                            help='to refresh patrol materialized view or create new one if does not exist')
        parser.add_argument('-d', '--drop-view',  action='store_true',
                            help='drop patrol materialized view if exists')
        parser.add_argument('-rc', '--recreate-view',  action='store_true',
                            help='recreate patrol materialized view')
