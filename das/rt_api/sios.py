'''This is the full socket io server with realtime services initializes'''
import logging

from django.conf import settings

import rt_api.server
from rt_api.socketio import RTSocketIO
import rt_api.pubsub_listener
import utils.json


logger = logging.getLogger('rt_api')


def create_rt_socketio(wsgi_handler):
    rtsios = RTSocketIO(app=wsgi_handler,
                      message_queue=settings.REALTIME_BROKER_URL,
                      json=utils.json,
                      logger=logger,
                      engineio_logger=logger)
    realtime_services = rt_api.server.create_realtime_handler(rtsios)
    rt_api.pubsub_listener.start(realtime_services)

    return rtsios