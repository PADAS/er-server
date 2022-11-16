"""
TODO: It will be better to create class-based namespaces, which formally allow hooking
into trigger_event.
"""

from typing import Iterable

from engineio.server import Server as EngineIOServer
from socketio.server import Server as SocketIOServer

from utils.db.connections import close_old_shared_connections


class DasEngineIOServer(EngineIOServer):
    def set_cors_allowed_origins(self, cors_allowed_origins: Iterable[str]):
        if isinstance(cors_allowed_origins, str) or not isinstance(cors_allowed_origins, Iterable):
            raise TypeError("Setting invalid CORS allowed origin list", cors_allowed_origins)

        new_cors_allowed_origins = list(cors_allowed_origins)
        if not new_cors_allowed_origins:
            raise ValueError("Setting empty list of CORS allowed origins")

        self.cors_allowed_origins = new_cors_allowed_origins


class DasSocketIOServer(SocketIOServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def set_cors_allowed_origins(self, cors_allowed_origins: Iterable[str]):
        self.eio.set_cors_allowed_origins(cors_allowed_origins)

    def _engineio_server_class(self):
        """
        Injects a DAS custom class implementing Engine IO
        """
        return DasEngineIOServer

    def _trigger_event(self, event, namespace, *args):
        """
        Extends socketio.server.Server, to implement _trigger_event.
        """
        try:
            super()._trigger_event(event, namespace, *args)
        finally:
            close_old_shared_connections()
