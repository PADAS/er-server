import inspect
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from threading import local

import pytz
from oauth2_provider.models import get_access_token_model
from oauthlib.common import generate_token
from opentelemetry import trace

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from rest_framework import status

from core import persistent_storage
from core.models.oauth import DASAccessToken, DASApplication
from observations.utils import (
    LOCATION,
    block_user_temp,
    get_position,
    get_user_key,
    is_banned,
)
from utils import add_base_url, stats
from utils.categories import should_apply_geographic_features
from utils.gis import convert_to_point
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import set_tenant_by_request

AccessToken = get_access_token_model()

logger = logging.getLogger(__name__)

request_data = local()

ACTIVITY_EVENTS_PATH_REGEX = (
    r"^\/api\/v1.0\/activity\/events?\/?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?\/?$"
)
EFB_APPLICATION_ID = "EFB_APPLICATION_ID"
EFB_ACCESS_TOKEN_NAME = "efb_access_token"
EFB_COOKIE_NAME = "efb_access_token"


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

    def process_response(self, request, response):
        try:
            remote_addr = request.META.get("REMOTE_ADDR")
            remote_addr = request.META.get("HTTP_X_FORWARDED_FOR") or remote_addr
            user_id = "-"
            if hasattr(request, "user"):
                user_id = getattr(request.user, "id", "-")
            try:
                req_time = time.time() - self.start_time
            except AttributeError:
                req_time = 0
            profile_id = request.META.get("HTTP_USER_PROFILE", "-")
            content_length = len(getattr(response, "content", []))
            referer = request.META.get("HTTP_REFERER", "")
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            status_code = response.status_code
            path = request.get_full_path()
            # Strip query parameters for cleaner metrics
            path_for_metrics = request.path
            host = request.get_host()
            method = request.method
            protocol = request.META.get("SERVER_PROTOCOL", "")
            language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
            try:
                tenant_domain = get_tenant_settings().domain
            except TenantNotFoundException:
                tenant_domain = "unknown"

            error_message = self._get_error_message(response=response, status_code=status_code)

            extra = dict(
                remote_addr=remote_addr,
                user_id=user_id,
                profile_id=profile_id,
                req_time=req_time,
                content_length=content_length,
                referer=referer,
                user_agent=user_agent,
                status=status_code,
                path=path,
                method=method,
                protocol=protocol,
                tenant=tenant_domain,
                host=host,
                language=language,
            )

            if error_message:
                extra["error_message"] = error_message

            self.logger.info("request", extra=extra)
            stats.histogram(
                "api_request_time",
                req_time,
                tags=[f"http_path:{path_for_metrics}", f"http_method:{method}", f"http_status:{status_code}"],
            )

            span = trace.get_current_span()
            span.set_attribute("er.tenant", tenant_domain)

        except Exception:
            logging.exception("RequestLoggingMiddleware Error")

        return response

    def _get_error_message(self, response, status_code):
        error_message = None
        data = getattr(response, "data", {})
        if isinstance(data, dict):
            error_message = data.get("error_message")

        if status_code >= status.HTTP_400_BAD_REQUEST:
            data = getattr(response, "data", {"status": {}})
            if isinstance(data, dict):
                error_message = error_message or str(data.get("status", {}).get("detail", ""))
            if not error_message:
                # our response data is not standardised at this point, log all of it
                error_message = str(getattr(response, "data", ""))
        return error_message

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
            position = json.dumps(
                {
                    "datetime": datetime.timestamp(now),
                    "position": {
                        "latitude": point.y,
                        "longitude": point.x,
                    },
                }
            )

            last_item = get_position(key)

            # Save position only if the newest is greater than one minute regardless
            # the location is the same as previous
            if last_item:
                last_item_point = convert_to_point(last_item.get("position"))
                if last_item_point == point:
                    last_item_datetime = datetime.fromtimestamp(last_item.get("datetime"), tz=pytz.UTC)
                    if int((now - last_item_datetime).seconds / 60) > 0:
                        persistent_storage.insert_in_sorted_set(key, position, datetime.timestamp(now))
                else:
                    persistent_storage.insert_in_sorted_set(key, position, datetime.timestamp(now))
            else:
                persistent_storage.insert_in_sorted_set(key, position, datetime.timestamp(now))


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
        accept_eula = get_tenant_settings().env_settings.accept_eula

        if accept_eula and is_check_eula_path(request.path) and user.is_authenticated and not user.accepted_eula:
            response = redirect(add_base_url(request, "/#eula"))
            response.set_cookie("routeAfterEulaAccepted", "/admin/")
            AccessToken = get_access_token_model()
            expires = timezone.now() + timedelta(minutes=20)
            access_token = AccessToken.objects.create(user=user, token=str(uuid.uuid4()), expires=expires)

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
            request.method == "GET"
            and re.search(ACTIVITY_EVENTS_PATH_REGEX, request.path)
            and not request.GET.get("location")
            and should_apply_geographic_features(user)
        ):
            warn_text = (
                "The required 'location' parameter is either invalid or missing."
                " Some data may be excluded from results."
            )
            response["Warning"] = f"199 - {warn_text}"

        if is_banned(user) and (re.search(ACTIVITY_EVENTS_PATH_REGEX, request.path)):
            warn_text = (
                "199 - You have violated the maximum speed configured."
                " Please wait a little while before trying again, or contact "
                "your site administrator with any questions."
            )
            response["Warning"] = warn_text
        return response


class TenantSettingsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            set_tenant_by_request(request=request)
        except TenantNotFoundException as ex:
            return JsonResponse(
                data={
                    "message": f"Your site configuration appears to be invalid: {ex}. Contact EarthRanger technical support for assistance."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        response = self.get_response(request)
        return response


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if features.tms.is_on():
            timezone_name = get_tenant_settings().time_zone
            if timezone_name:
                timezone.activate(pytz.timezone(timezone_name))
        return self.get_response(request)


def is_check_eula_path(path):
    return path == "/admin/"


class ManageAdminEFBTokenMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if self._should_create_efb_token(request, response):
            if token := DASAccessToken.objects.filter(
                application__client_id=EFB_APPLICATION_ID,
                user=request.user,
                expires__gt=timezone.now(),
            ).first():
                response.set_cookie(EFB_COOKIE_NAME, token.token, samesite="Lax", secure=True)

            else:
                self._create_efb_token(request, response)

        if "/admin/logout" in request.path:
            self._invalidate_efb_token(request, response)

        return response

    def _should_create_efb_token(self, request, response):
        return (
            "/admin/login" in request.path
            and request.user.is_authenticated
            and request.user.is_staff
            and not response.has_header("Set-Cookie")
            and "_auth_user_id" in request.session
            and request.session["_auth_user_id"] == str(request.user.pk)
        )

    def _invalidate_efb_token(self, request, response):
        user = request.user

        if EFB_ACCESS_TOKEN_NAME not in request.COOKIES:
            if user.is_authenticated:
                DASAccessToken.objects.filter(application__client_id=EFB_APPLICATION_ID, user=user).delete()
            return

        try:
            DASAccessToken.objects.filter(
                application__client_id=EFB_APPLICATION_ID, token=request.COOKIES.get(EFB_ACCESS_TOKEN_NAME)
            ).delete()

            response.delete_cookie(EFB_ACCESS_TOKEN_NAME)
            del request.COOKIES[EFB_ACCESS_TOKEN_NAME]

            logger.info(f"Invalidated access token {EFB_ACCESS_TOKEN_NAME} for user {user.username}")

        except Exception as e:
            logger.warning(f"Error: {e} invalidating {EFB_ACCESS_TOKEN_NAME} {e}")

    def _create_efb_token(self, request, response):
        try:
            efb_app = DASApplication.objects.get(
                client_id=EFB_APPLICATION_ID,
            )
        except DASApplication.DoesNotExist:
            logger.warning(
                "EFB application with client_id %s does not exist in tenant %s",
                EFB_APPLICATION_ID,
                get_tenant_settings().domain,
            )
            return

        try:
            oauth2_settings = getattr(settings, "OAUTH2_PROVIDER", {})
            expire_in_secs = oauth2_settings.get("ACCESS_TOKEN_EXPIRE_SECONDS")
            expires = timezone.now() + timedelta(seconds=expire_in_secs)

            access_token = DASAccessToken.objects.create(
                user=request.user,
                token=generate_token(),
                application=efb_app,
                expires=expires,
                scope="read write",
                das_tenant=request.user.das_tenant,
            )
            logger.debug(
                "Middleware: Created access token for user %s at %s",
                request.user.username,
                EFB_ACCESS_TOKEN_NAME,
            )

            response.set_cookie(EFB_COOKIE_NAME, access_token.token, samesite="Lax", secure=True)

        except Exception as e:
            logger.error(f"Middleware: Error creating token: {e}")
