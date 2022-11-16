from django.core.management.base import BaseCommand

from das_server.pubsub import (
    start_gcloud_pubsub_listener,
    start_message_queue_listeners,
)


class Command(BaseCommand):

    help = "Start pubsub infrastructure: exchange, queues and consumers."

    def handle(self, *args, **options):
        start_gcloud_pubsub_listener()
        start_message_queue_listeners()
