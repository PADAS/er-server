import logging

from rest_framework_gis.pagination import GeoJsonPagination

import django.views.defaults
import rest_framework
from django.core.paginator import Paginator
from django.db import OperationalError, connection, transaction
from django.http import JsonResponse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
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
        str(_('Internal Server Error'))
        detail = str(exc)
        data = {'detail': detail} if detail else {}
        set_rollback()
        response = Response(data,
                            status=rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR)
    return fixup_api_response(response)


class OptionalResultsSetPagination(PageNumberPagination):
    page_size_query_param = 'page_size'


class StandardResultsSetPagination(OptionalResultsSetPagination):
    page_size = 25
    max_page_size = 4000


class StandardResultsSetGeoJsonPagination(GeoJsonPagination):
    page_size = 25


class AllowAnyGet(BasePermission):
    def has_permission(self, request, view):
        return request.method in ('GET', 'HEAD', 'OPTIONS') \
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
