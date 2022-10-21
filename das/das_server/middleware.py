from django.conf import settings
from django.core.handlers.base import BaseHandler
from django.http import HttpResponsePermanentRedirect
from django.middleware.common import CommonMiddleware
from django.utils.http import escape_leading_slashes


class HttpSmartRedirectResponse(HttpResponsePermanentRedirect):
    pass


class CommonMiddlewareAppendSlashWithoutRedirect(CommonMiddleware):
    """
        This class converts HttpSmartRedirectResponse to the common response
        of Django view, without redirect. This is necessary to match status_codes
        for urls like /url?q=1 and /url/?q=1. If you don't use it, you will have 302
        code always on pages without slash.
    """
    response_redirect_class = HttpSmartRedirectResponse

    def __init__(self, get_response=None):
        # create django request resolver
        self.handler = BaseHandler()

        # prevent recursive includes
        old = settings.MIDDLEWARE
        name = f"{self.__module__}.{self.__class__.__name__}"
        settings.MIDDLEWARE = [i for i in settings.MIDDLEWARE if i != name]

        self.handler.load_middleware()

        settings.MIDDLEWARE = old
        super().__init__(get_response)

    def get_full_path_with_slash(self, request):
        """
            Return the full path of the request with a trailing slash appended
            without Exception in Debug mode
        """
        old_path = request.get_full_path(force_append_slash=True)
        # Prevent construction of scheme relative urls.
        new_path = escape_leading_slashes(old_path)
        return new_path

    def process_response(self, request, response):
        response = super().process_response(request, response)

        if isinstance(response, HttpSmartRedirectResponse):
            if not request.path.endswith('/'):
                request.path = request.path + '/'
            # we don't need query string in path_info because it's in request.GET already
            request.path_info = request.path
            response = self.handler.get_response(request)

        return response
