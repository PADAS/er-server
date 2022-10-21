from django.core.management.base import BaseCommand

import rt_api.client as client


class Command(BaseCommand):
    help = 'Realtime session manager utility'

    def add_arguments(self, parser):
        # Allow one of the following options
        g = parser.add_mutually_exclusive_group()
        g.add_argument(
            '--add_user',
            action='store_true',
            dest='add_test_user',
            help='Add ',
        )

        g.add_argument(
            '--reset_conns',
            action='store_true',
            dest='reset_connections',
            help='Remove all current realtime connections from redis',
        )

        g.add_argument(
            '--list_services',
            action='store_true',
            dest='services',
            help='List all realtime services',
        )

        g.add_argument(
            '--list_conns',
            action='store_true',
            dest='list',
            help='List all realtime connections',
        )

    def handle(self, *args, **options):

        if options['add_test_user']:
            self.add_test_user()
            print("added user")

        elif options['reset_connections']:
            self.delete_all()

        elif options['services']:
            self.list_services()

        elif options['list']:
            self.list_connections()

    def add_test_user(self):
        testdata = client.ClientData(sid='e8ef807c2bbe4418b32de45786d82a52',
                                     username='admin',
                                     filter='{}',
                                     bbox=None)
        client.add_client(testdata.sid, testdata)

    def delete_all(self):
        client.remove_all_rt_services()

    def list_services(self):
        for service in client.get_rt_service_list():
            print(service)

    def list_connections(self):
        for sess_data in client.get_client_list():
            print(sess_data)
