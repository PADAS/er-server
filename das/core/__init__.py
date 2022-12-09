from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class ClientProxy:
    def __init__(self, config: dict, service_name: str):
        self._client = None
        self._config = config
        self._service_name = service_name

    def __getattr__(self, item):
        return getattr(self.client, item)

    @property
    def client(self):
        if not self._client:
            self._client = self._build_client()

        return self._client

    def _build_client(self):
        try:
            config = self._config
        except AttributeError:
            raise ImproperlyConfigured(f"Missing {self._service_name} settings")

        params = {**config}
        client = params.pop("CLIENT")

        try:
            client_cls = import_string(client)
        except ImportError as error:
            raise ImproperlyConfigured(f"Could not find backend {client}: {error}")

        return client_cls(params)


persistent_storage = ClientProxy(config=settings.PERSISTENT_STORAGE, service_name="PERSISTENT_STORAGE")
tms_api_client = ClientProxy(config=settings.TMS_API, service_name="TMS_API")
