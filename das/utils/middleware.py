import inspect
import logging
import time
import uuid
from datetime import timedelta
from threading import local

from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone
from google.cloud import error_reporting
from google.cloud.exceptions import DefaultCredentialsError
from oauth2_provider.models import get_access_token_model
from utils import add_base_url

logger = logging.getLogger(__name__)


request_data = local()
error_reporting_client = None
try:
    error_reporting_client = error_reporting.Client()
except DefaultCredentialsError as ex:
    logger.warning(f"Initializing err_reporting_client: {ex}")


class RequestLoggingMiddleware(object):
    logger = logging.getLogger('django.request')

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        self.process_request(request)

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        return self.process_response(request, response)

    def process_request(self, request):
        self.start_time = time.time()

    def process_exception(self, request, exception):
        self.logger.exception('Exception handling %s', request.get_full_path)
        if error_reporting_client:
            error_reporting_client.report_exception(exception)

    def process_response(self, request, response):
        try:
            result = {}

            logname = '-'
            remote_addr = request.META.get('REMOTE_ADDR')
            remote_addr = request.META.get(
                'HTTP_X_FORWARDED_FOR') or remote_addr
            user_id = '-'
            if hasattr(request, 'user'):
                user_id = getattr(request.user, 'id', '-')
            try:
                req_time = time.time() - self.start_time
            except AttributeError:
                req_time = 0
            content_length = len(getattr(response, 'content', []))
            referer = request.META.get('HTTP_REFERER', '')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            status = response.status_code
            path = request.get_full_path()
            method = request.method
            protocol = request.META.get('SERVER_PROTOCOL', '')

            extra = dict(
                remote_addr=remote_addr,
                user_id=user_id,
                req_time=req_time,
                content_length=content_length,
                referer=referer,
                user_agent=user_agent,
                status=status,
                path=path,
                method=method,
                protocol=protocol,
            )

            request_info = '{0} {1} {2}'.format(method, path, protocol)
            method = '%s %s %s [] "%s" %s %s "%s" "%s" (%.02f seconds)' % (
                remote_addr, logname, user_id, request_info,
                status, content_length, referer, user_agent, req_time)

            self.logger.info('request', extra=extra)

        except Exception as e:
            logging.exception('RequestLoggingMiddleware Error')

        # stats.increment_for_view(request.resolver_match.view_name)

        return response


class RequestDataMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        request_data.view_name = None
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        module = inspect.getmodule(view_func).__name__
        request_data.view_name = f'{module}.{view_func.__name__}'


class EULARedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        return self.process_response(request, response)

    def process_response(self, request, response):
        user = request.user

        if settings.ACCEPT_EULA and is_check_eula_path(
                request.path) and user.is_authenticated and not user.accepted_eula:
            response = redirect(add_base_url(request, '/#eula'))
            response.set_cookie("routeAfterEulaAccepted", "/admin/")
            AccessToken = get_access_token_model()
            expires = timezone.now() + timedelta(minutes=20)
            access_token = AccessToken.objects.create(
                user=user, token=str(uuid.uuid4()), expires=expires)

            response.set_cookie("temporaryAccessToken", access_token.token)

            return response

        return response


def is_check_eula_path(path):
    return path == "/admin/"
