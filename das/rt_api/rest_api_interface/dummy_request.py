# from oauthlib.common import Request
from oauthlib.common import CaseInsensitiveDict, extract_params, to_unicode

from django.http.request import HttpRequest
from rest_framework.request import Request
from rest_framework.settings import api_settings

from utils.tenant import get_tenant_settings


def wrap_dummy_request_with_drf_request(dummy_request):
    """Wrap a DummyRequest in a DRF Request, applying DRF authentication classes."""
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    return Request(request=dummy_request, authenticators=[auth() for auth in authentication_classes])


class DummyRequest(HttpRequest):
    _request = None

    @staticmethod  # Convert to unicode using encoding if given, else assume unicode
    def encode(x, encoding=None):
        return to_unicode(x, encoding) if encoding else x

    def __init__(
        self, uri="/dummy", http_method="POST", body={}, headers={}, encoding="utf-8", user=None, query_parameters=None
    ):
        super().__init__()
        self.host = get_tenant_settings().domain
        self.uri = self.encode(uri)
        self.http_method = self.encode(http_method)
        self.headers = CaseInsensitiveDict(self.encode(headers or {}))
        self._body = self.encode(body)
        self.decoded_body = extract_params(self.body)

        self.method = self.http_method
        self.META = headers
        self.POST = body
        self.encoding = encoding
        self._request = self
        self.query_params = query_parameters or {}
        self.GET = self.query_params
        self.successful_authenticator = "dummy_authentication"
        self.user = user
        self._force_auth_user = user

    def get_full_path(self):
        return self.uri

    def build_absolute_uri(self, url=None):
        return url

    def copy(self, *args):
        pass

    def get_host(self):
        return self.host
