'''This is the full socket io server with realtime services initializes'''
import logging

from django.conf import settings
from socketio.kombu_manager import KombuManager

import rt_api.server
from rt_api.socketio import RTSocketIO
import rt_api.pubsub_listener
import utils.json


logger = logging.getLogger('rt_api')


def create_rt_socketio(wsgi_handler):
    client_mgr = KombuManager(url=settings.REALTIME_BROKER_URL,
                              transport_options = settings.REALTIME_BROKER_OPTIONS
                              )
    rtsios = RTSocketIO(app=wsgi_handler,
                      client_manager=client_mgr,
                      json=utils.json,
                      logger=logger,
                      engineio_logger=logger)
    realtime_services = rt_api.server.create_realtime_handler(rtsios)
    rt_api.pubsub_listener.start(realtime_services)

    return rtsios