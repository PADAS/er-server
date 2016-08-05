
from oauthlib.common import Request

class DummyRequest(Request):
    _request = None
    def __init__(self, uri='/dummy', http_method='POST', body={}, headers={}, encoding='utf-8', user = None):
        Request.__init__(self, uri, http_method, body, headers, encoding)

        self.method = http_method
        self.META = headers
        self.POST = body
        self.GET = body
        self.encoding = encoding
        self._request = self
        self.query_params = {}
        self.successful_authenticator = 'dummy_authentication'
        self._authenticator = 'dummy_authenticatior'
        self._user = user
        self.user = user
        self._force_auth_user = user


    def get_full_path(self):
        return self.uri

    def build_absolute_uri(self, url):
        return url

    def copy(self, *args):
        pass
