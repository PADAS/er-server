from django.core.management.base import BaseCommand

from reports.tasks import subjectsource_report


class Command(BaseCommand):

    help = 'Create and distribute Source Report.'

    def handle(self, *args, **options):

        subjectsource_report(usernames=options['usernames'])

    def add_arguments(self, parser):
        parser.add_argument(
            '-u', '--usernames',
            nargs='+',
            action='store',
            dest='usernames',
            default=None,
            help='Usernames for whom you want to generate and send report. Defaults to all users in report permissionset.',
        )
