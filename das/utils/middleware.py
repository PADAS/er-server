import inspect
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from threading import local

import pytz
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import error_reporting
from oauth2_provider.models import get_access_token_model

from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone

from core import persistent_storage
from observations.utils import (LOCATION, block_user_temp, get_position,
                                get_user_key, is_banned)
from utils import add_base_url, stats
from utils.categories import should_apply_geographic_features
from utils.gis import convert_to_point

logger = logging.getLogger(__name__)

request_data = local()

try:
    error_reporting_client = error_reporting.Client()
except DefaultCredentialsError as ex:
    error_reporting_client = None
    logger.warning(f"Initializing err_reporting_client: {ex}")

ACTIVITY_EVENTS_PATH_REGEX = r"^\/api\/v1.0\/activity\/events?\/?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?\/?$"


class RequestLoggingMiddleware(object):
    logger = logging.getLogger("django.request")

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
        self._save_location(request)
        block_user_temp(request.user)
        self.start_time = time.time()

    def process_exception(self, request, exception):
        self.logger.exception("Exception handling %s", request.get_full_path)
        if error_reporting_client:
            error_reporting_client.report_exception(exception)

    def process_response(self, request, response):
        try:
            logname = '-'
            remote_addr = request.META.get('REMOTE_ADDR')
            remote_addr = request.META.get(
                "HTTP_X_FORWARDED_FOR") or remote_addr
            user_id = "-"
            if hasattr(request, "user"):
                user_id = getattr(request.user, "id", "-")
            try:
                req_time = time.time() - self.start_time
            except AttributeError:
                req_time = 0
            content_length = len(getattr(response, "content", []))
            referer = request.META.get("HTTP_REFERER", "")
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            status = response.status_code
            path = request.get_full_path()
            method = request.method
            protocol = request.META.get("SERVER_PROTOCOL", "")

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

            request_info = "{0} {1} {2}".format(method, path, protocol)
            method = '%s %s %s [] "%s" %s %s "%s" "%s" (%.02f seconds)' % (
                remote_addr,
                logname,
                user_id,
                request_info,
                status,
                content_length,
                referer,
                user_agent,
                req_time,
            )

            self.logger.info('request', extra=extra)
            stats.histogram('api_request_time', req_time,
                            tags=[
                                f'path:{path}',
                                f'method:{method}'
                                f'satus:{status}'
                            ]
                            )

        except Exception:
            logging.exception('RequestLoggingMiddleware Error')

        # stats.increment_for_view(request.resolver_match.view_name)

        return response

    def _save_location(self, request):
        if (
                request.user
                and should_apply_geographic_features(request.user)
                and re.search(ACTIVITY_EVENTS_PATH_REGEX, request.path)
                and "location" in request.GET
        ):
            now = timezone.now()
            key = get_user_key(request.user, LOCATION)
            point = convert_to_point(request.GET.get("location"))
            position = json.dumps({
                "datetime": datetime.timestamp(now),
                "position": {
                    "latitude": point.y,
                    "longitude": point.x,
                },
            })

            last_item = get_position(key)

            # Save position only if the newest is greater than one minute regardless
            # the location is the same as previous
            if last_item:
                last_item_point = convert_to_point(last_item.get("position"))
                if last_item_point == point:
                    last_item_datetime = datetime.fromtimestamp(
                        last_item.get("datetime"), tz=pytz.UTC)
                    if int((now - last_item_datetime).seconds / 60) > 0:
                        persistent_storage.insert_in_sorted_set(
                            key, position, datetime.timestamp(now))
                else:
                    persistent_storage.insert_in_sorted_set(
                        key, position, datetime.timestamp(now))
            else:
                persistent_storage.insert_in_sorted_set(
                    key, position, datetime.timestamp(now))


class RequestDataMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        request_data.view_name = None
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        module = inspect.getmodule(view_func).__name__
        request_data.view_name = f"{module}.{view_func.__name__}"


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

        if (
                settings.ACCEPT_EULA
                and is_check_eula_path(request.path)
                and user.is_authenticated
                and not user.accepted_eula
        ):
            response = redirect(add_base_url(request, "/#eula"))
            response.set_cookie("routeAfterEulaAccepted", "/admin/")
            AccessToken = get_access_token_model()
            expires = timezone.now() + timedelta(minutes=20)
            access_token = AccessToken.objects.create(
                user=user, token=str(uuid.uuid4()), expires=expires
            )

            response.set_cookie("temporaryAccessToken", access_token.token)

            return response

        return response


class GeographicMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request, *args, **kwargs):
        response = self.get_response(request)
        user = request.user

        if user.is_superuser:
            return response

        if (
                request.method == 'GET'
                and should_apply_geographic_features(user)
                and not request.GET.get("location")
                and re.search(ACTIVITY_EVENTS_PATH_REGEX, request.path)
        ):
            warn_text = (
                "The required 'location' parameter is either invalid or missing."
                " Some data may be excluded from results."
            )
            response["Warning"] = f"199 - {warn_text}"

        if is_banned(user) and (re.search(ACTIVITY_EVENTS_PATH_REGEX, request.path)):
            warn_text = (
                f"199 - You have violated the maximum speed configured."
                f" Please wait a little while before trying again, or contact "
                f"your site administrator with any questions."
            )
            response["Warning"] = warn_text
        return response


def is_check_eula_path(path):
    return path == "/admin/"
