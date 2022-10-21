import hashlib
import logging

from rest_framework_gis.pagination import GeoJsonPagination

import django.views.defaults
import rest_framework
from django.conf import settings
from django.core.cache import caches
from django.core.paginator import Paginator
from django.db import OperationalError, connection, transaction
from django.http import JsonResponse
from django.utils.functional import cached_property
from rest_framework import exceptions
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

logger = logging.getLogger('django.request')


def fixup_api_response(response):
    """The DAS api returns a json error payload"""
    if response:
        detail = response.data.pop('detail', None)
        status = {'code': response.status_code,
                  'message': response.status_text,
                  }
        if detail:
            status['detail'] = detail
        response.data['status'] = status
    return response


def error404View(request, exception, template_name='404.html'):
    """Handle 404 in our api"""
    if not request.path.startswith('/api/v1.0/'):
        return django.views.defaults.page_not_found(request, exception, template_name=template_name)

    # Create a Response with an appropriate status-code here, then let the fixup function codify it in the
    # resposne body.
    response = Response({}, status=rest_framework.status.HTTP_404_NOT_FOUND)
    response = fixup_api_response(response)

    response = JsonResponse(data=response.data,
                            status=rest_framework.status.HTTP_404_NOT_FOUND)
    return response


def api_exception_handler(exc, context):
    """
    Our custom error handler, that returns payload as JSON
    """
    if not isinstance(exc, (exceptions.PermissionDenied,
                            exceptions.NotAuthenticated,
                            exceptions.AuthenticationFailed,
                            )):
        logger.exception('Exception handling %s',
                         context['request'].get_full_path())
    # TODO: there is a case where drf returns data as a list or a dictionary
    # without putting it in a new dictionary under the "datail" key which breaks fixup_api_response
    response = exception_handler(exc, context)
    if not response:
        detail = str(exc)
        data = {'detail': detail} if detail else {}
        set_rollback()
        response = Response(data,
                            status=rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR)
    return fixup_api_response(response)


class OptionalResultsSetPagination(PageNumberPagination):
    page_size_query_param = 'page_size'


class StandardResultsSetPagination(OptionalResultsSetPagination):
    page_size = settings.REST_FRAMEWORK["OPTIONAL_PAGE_SIZE"]
    max_page_size = settings.REST_FRAMEWORK["MAX_PAGE_SIZE"]


class StandardResultsSetGeoJsonPagination(GeoJsonPagination):
    page_size = settings.REST_FRAMEWORK["OPTIONAL_PAGE_SIZE"]


class StandardResultsSetCursorPagination(CursorPagination):
    page_size_query_param = 'page_size'
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


def patch_queryset_with_cached_count(queryset, timeout: int = 60*60, cache_name: str = 'default'):
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
        if hasattr(queryset, 'count'):
            queryset = patch_queryset_with_cached_count(
                queryset, timeout=self.count_timeout)
        return super().paginate_queryset(queryset, *args, **kwargs)


class AllowAnyGet(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS \
            or (request.user and request.user.is_authenticated)


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
            cursor.execute('SET LOCAL statement_timeout TO 200;')
            try:
                return super().count
            except OperationalError:
                return 9999999999
