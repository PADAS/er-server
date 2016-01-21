""" routes messages on the message queue to handlers
all routing_key -> handler mapping currently is defined
in here, you may want to make this more flexible
"""

import logging

from django.core.management.base import BaseCommand
from kombu import Connection, Exchange, Queue

from das_server import pubsub
from das_server.celery_settings import BROKER_URL


logger = logging.getLogger(__name__)

def callback(body, message):
    """ generic kombu callback, just prints body and message """
    msg = "callback message: {} body: {}".format(message, body)
    print(msg)


class Command(BaseCommand):

    help = 'routes messages on the message queue to handlers'

    def handle(self, *args, **options):

        # configure key / handler mapping somewhere less deep
        routing_key = 'das.#'
        pubsub.subscribe(routing_key=routing_key, callback=callback)

