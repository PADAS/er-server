import sys

from redis.exceptions import ConnectionError
from socketio.kombu_manager import KombuManager


class DASKombuManager(KombuManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _thread(self):
        try:
            self._get_logger().info("Starting Kombu manager thread...")
            result = super()._thread()
            self._get_logger().info("Ending Kombu manager thread...")
            return result

        except ConnectionError:
            self._get_logger().exception("RT API server has to die, so EarthRanger will prevail...")
            sys.exit(1)
        except Exception:
            self._get_logger().exception("Ending Kombu manager thread unexpectedly...")
            raise
