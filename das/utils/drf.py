import hashlib
import logging
from typing import Dict, List, Optional, Union
from urllib.parse import quote

from rest_framework_gis.pagination import GeoJsonPagination

import django.views.defaults
from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.paginator import InvalidPage, Paginator
from django.db import OperationalError, connection, transaction
from django.db.models.query import QuerySet
from django.http import HttpResponse, JsonResponse
from django.http.request import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView, exception_handler, set_rollback

logger = logging.getLogger("django.request")


def fixup_api_response(response):
    """The DAS api returns a json error payload"""
    if response:
        if isinstance(response.data, list):  # validation errors return a list of errors
            return response
        detail = response.data.pop("detail", None)
        status = {
            "code": response.status_code,
            "message": response.status_text,
        }
        if detail:
            status["detail"] = detail
        response.data["status"] = status
    return response


def error404View(request, exception, template_name="404.html"):
    """Handle 404 in our api"""
    if not request.path.startswith("/api/v1.0/"):
        return django.views.defaults.page_not_found(request, exception, template_name=template_name)

    # Create a Response with an appropriate status-code here, then let the fixup function codify it in the
    # resposne body.
    response = Response({}, status=status.HTTP_404_NOT_FOUND)
    response = fixup_api_response(response)

    response = JsonResponse(data=response.data, status=status.HTTP_404_NOT_FOUND)
    return response


def api_exception_handler(exc, context):
    """
    Our custom error handler, that returns payload as JSON
    """
    if not isinstance(
        exc,
        (
            exceptions.PermissionDenied,
            exceptions.NotAuthenticated,
            exceptions.AuthenticationFailed,
            exceptions.APIException,
        ),
    ):
        # if it's not a known exception, log it
        logger.exception("Exception handling %s", context["request"].get_full_path())

    # TODO: there is a case where drf returns data as a list or a dictionary
    # without putting it in a new dictionary under the "detail" key which breaks fixup_api_response
    response = exception_handler(exc, context)
    if not response:
        detail = str(exc)
        data = {"detail": detail} if detail else {}
        set_rollback()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        if isinstance(exc, ValidationError):
            try:
                data = {"detail": exc.message_dict} if detail else {}
            except AttributeError:
                pass

            status_code = status.HTTP_400_BAD_REQUEST

        response = Response(data, status=status_code)
    return fixup_api_response(response)


class CachedCountPaginator(Paginator):

    def __init__(self, count_cache_key: str, cache_timeout: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.count_cache_key = count_cache_key
        self.cache_timeout = cache_timeout

    @cached_property
    def count(self):
        cache = caches["default"]
        value = cache.get(self.count_cache_key)
        if value or value == 0:
            return value

        value = super().count
        cache.set(self.count_cache_key, value, self.cache_timeout)
        return value


class TimeLimitedPaginator(Paginator):
    """
    Paginator that enforced a timeout on the count operation.
    When the timeout is reached a "fake" large value is returned instead,
    Why does this hack exist? On every admin list view, Django issues a
    COUNT on the full queryset. There is no simple workaround. On big tables,
    this COUNT is extremely slow and makes things unbearable. This solution
    is what we came up with.
    https://hakibenita.com/optimizing-the-django-admin-paginator
    """

    @cached_property
    def count(self):
        # We set the timeout in a db transaction to prevent it from
        # affecting other transactions.
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout TO 200;")
            try:
                return super().count
            except OperationalError:
                return 9999999999


class OptionalResultsSetPagination(PageNumberPagination):
    page_size_query_param = "page_size"


class StandardResultsSetPagination(OptionalResultsSetPagination):
    page_size = settings.REST_FRAMEWORK["OPTIONAL_PAGE_SIZE"]
    max_page_size = settings.REST_FRAMEWORK["MAX_PAGE_SIZE"]


def get_sorted_query_parameters(query_parameters: QueryDict) -> dict:
    """
    Let's sort the query parameters to generate a consistent dictionary, this is useful for caching or generating an
    id for the request
    """
    sorted_query_parameters = {}

    for key in sorted(query_parameters.keys()):
        value = query_parameters.getlist(key)
        if len(value) > 1:
            sorted_query_parameters[key] = ",".join(sorted(value))
        else:
            sorted_query_parameters[key] = value[0]

    return sorted_query_parameters


def sorted_query_parameters_to_string(query_parameters: Union[QueryDict, Dict]) -> str:
    """
    Main idea behind this is to generate a constant string that can be used as a cache key for example,
    """
    if isinstance(query_parameters, QueryDict):
        query_parameters = get_sorted_query_parameters(query_parameters)

    return "&".join([f"{key}={quote(value)}" for key, value in query_parameters.items()])


class CachedCountResultsSetPagination(StandardResultsSetPagination):
    """
    This paginator caches the count of the queryset for a given timeout,
    this is useful when the count operation is expensive...

    The cache key is generated using the user, the path of the request and the query parameters that can affect the
    number of items in the response.

    The list of parameters that can be ignored when generating the cache key can be set in the view by setting the
    `page_count_ignored_query_parameters` attribute to a list of strings.
    """

    cache_timeout = 60 * 15  # 15 minutes
    cache_key = "{cache_prefix}:{user}:{path}:{query_parameters}"
    cache_prefix = "pgn"

    def get_parameters_for_cache_key(self, request: Request, view: Optional[APIView] = None) -> dict:
        # We will take care of the user, the urlpath and the query parameters that can affect the number of items in
        # the response, we will ignore the query parameters that can affect the order of the items in the response
        ignored_query_parameters = {self.page_query_param, api_settings.ORDERING_PARAM}

        if view:
            ignored_query_parameters.update(getattr(view, "page_count_ignored_query_parameters", []))

        query_parameters = request.query_params.copy()
        for parameter in ignored_query_parameters:
            query_parameters.pop(parameter, None)

        return query_parameters

    def get_cache_key(self, request: Request, view: Optional[APIView] = None) -> str:
        query_parameters = self.get_parameters_for_cache_key(request, view)
        clean_path = request.get_full_path().split("?")[0]

        return self.cache_key.format(
            cache_prefix=self.cache_prefix,
            user=str(request.user.id),
            path=clean_path,
            query_parameters=sorted_query_parameters_to_string(query_parameters),
        )

    def paginate_queryset(
        self, queryset: QuerySet, request: Request, view: Optional[APIView] = None
    ) -> Optional[Union[List, QuerySet]]:
        """
        Copied from the DRF source code but using our own paginator class
        """
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        cache_key = self.get_cache_key(request, view)
        paginator = CachedCountPaginator(cache_key, self.cache_timeout, queryset, page_size)
        page_number = request.query_params.get(self.page_query_param, 1)
        if page_number in self.last_page_strings:
            page_number = paginator.num_pages

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(page_number=page_number, message=str(exc))
            raise exceptions.NotFound(msg)

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.request = request
        return list(self.page)


class StandardResultsSetGeoJsonPagination(GeoJsonPagination):
    page_size = settings.REST_FRAMEWORK["OPTIONAL_PAGE_SIZE"]


class StandardResultsSetCursorPagination(CursorPagination):
    page_size_query_param = "page_size"
    page_size = settings.REST_FRAMEWORK["OPTIONAL_PAGE_SIZE"]

    def get_custom_page_size(self, request, view):
        try:
            self.page_size = int(request.GET.get("page_size"))
        except (ValueError, TypeError):
            pass
        return super().get_page_size(request)

    def paginate_queryset(self, queryset, request, view=None):
        self.page_size = self.get_custom_page_size(request, view)
        return super().paginate_queryset(queryset, request, view)


def patch_queryset_with_cached_count(queryset, timeout: int = 60 * 60, cache_name: str = "default"):
    """Return queryset with queryset.count() wrapped to cache the calculated count for `timeout` seconds.
       Credit: jcushman https://github.com/encode/django-rest-framework/issues/2650

    Args:
        queryset: queryset that is to be patched with our own count function
        timeout (int, optional): how long should the cache live in seconds. Defaults to 60*60.
        cache_name (str, optional): allows to overide the django cache namespace used to store our queryset count. Defaults to 'default'.

    Returns:
        queryset: the same queryset, now patched with our own count function
    """
    cache = caches[cache_name]
    queryset = queryset._chain()
    real_count = queryset.count

    def _get_query_count_key(queryset):
        return f"query-count: {hashlib.md5(str(queryset.query).encode('utf8')).hexdigest()}"

    def count(queryset):
        cache_key = _get_query_count_key(queryset)

        value = cache.get(cache_key)
        if value or value == 0:
            return value

        value = real_count()
        cache.set(cache_key, value, timeout)
        return value

    queryset.count = count.__get__(queryset, type(queryset))
    return queryset


class CachedCountStandardResultsSetPagination(StandardResultsSetPagination):
    count_timeout = settings.REST_FRAMEWORK["COUNT_TIMEOUT"]

    def paginate_queryset(self, queryset, *args, **kwargs):
        if hasattr(queryset, "count"):
            queryset = patch_queryset_with_cached_count(queryset, timeout=self.count_timeout)
        return super().paginate_queryset(queryset, *args, **kwargs)


class AllowAnyGet(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or (request.user and request.user.is_authenticated)


def return_409_response(message=None):
    status_msg = {
        "error_message": f"The request could not be completed due to conflict with existing data. ({message})"
    }
    return Response(status_msg, status=status.HTTP_409_CONFLICT)


class BadRequestAPIException(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("Bad request.")
    default_code = "error"


class ForbiddenAPIException(exceptions.APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Forbidden.")
    default_code = "error"


class CycleDetectedException(exceptions.APIException):
    status_code = 508
    default_detail = "Cyclic SubjectGroup found"
    default_code = "loop_detected"


def create_json_response(content, content_type="application/json"):
    """
    Create an HttpResponse with proper Content-Length header.

    Args:
        content: The content to return (string or bytes)
        content_type: The content type (default: application/json)

    Returns:
        HttpResponse with Content-Length header set
    """

    if isinstance(content, str):
        content = content.encode("utf-8")

    response = HttpResponse(content, content_type=content_type)
    response["Content-Length"] = str(len(content))
    return response


class ContentLengthMiddleware:
    """
    Middleware that automatically sets Content-Length headers for responses.
    This should be placed AFTER other middleware that might modify response content.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Always recalculate Content-Length to ensure accuracy
        # This handles cases where other middleware modified the response
        if response.streaming:
            pass
        elif hasattr(response, "content"):
            # Django HttpResponse - use the final content
            response["Content-Length"] = str(len(response.content))
        elif hasattr(response, "data"):
            # DRF Response - render to get final content
            try:
                rendered_content = response.render()
                response["Content-Length"] = str(len(rendered_content))
            except Exception:
                # Fallback: try to get content length from response
                if hasattr(response, "content"):
                    response["Content-Length"] = str(len(response.content))

        return response
