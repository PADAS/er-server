from django.core.management.base import BaseCommand
from das_server import pubsub


class Command(BaseCommand):

    help = 'Start pubsub infrastructure: exchange, queues and consumers.'

    def handle(self, *args, **options):

        pubsub.start_message_queue_listeners()
