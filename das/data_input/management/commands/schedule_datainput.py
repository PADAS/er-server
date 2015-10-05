from django.core.management.base import BaseCommand
from data_input import startup


class Command(BaseCommand):

    help = 'Start scheduler for data_input jobs.'

    def handle(self, *args, **kwargs):
        startup.start_scheduler()

        '''
        We run this command using supervisor, and we don't want it to terminate immediately. So we'll
        prompt to keep it going.
        '''
        ans = input("Type Ctrl+C to shutdown")
