from rest_framework.request import Request
from django.http.request import HttpRequest
#from oauthlib.common import Request
from oauthlib.common import to_unicode, CaseInsensitiveDict, extract_params


class DummyRequest(HttpRequest):
    _request = None

    @staticmethod  # Convert to unicode using encoding if given, else assume unicode
    def encode(x, encoding=None):
        return to_unicode(x, encoding) if encoding else x

    def __init__(self, uri='/dummy', http_method='POST', body={}, headers={}, encoding='utf-8',
                 user=None, query_parameters=None):
        super().__init__()

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
        self.successful_authenticator = 'dummy_authentication'
        self.user = user
        self._force_auth_user = user

    def get_full_path(self):
        return self.uri

    def build_absolute_uri(self, url=None):
        return url

    def copy(self, *args):
        pass
