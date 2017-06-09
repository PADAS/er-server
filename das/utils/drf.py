"""
Code found here:
Allow a superuser to browse the DRF api.
"""
import logging

import django.views.defaults
from django.http import Http404, JsonResponse
from django.utils.translation import ugettext_lazy as _
import rest_framework
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.compat import set_rollback
from rest_framework.response import Response
from rest_framework.views import exception_handler
from rest_framework.pagination import PageNumberPagination
from rest_framework.metadata import BaseMetadata


logger = logging.getLogger('django.request')


class SuperUserSessionAuthentication(SessionAuthentication):
    """
    Use Django's session framework for authentication of super users.
    """

    def authenticate(self, request):
        """
        Returns a `User` if the request session currently has a logged in user.
        Otherwise returns `None`.
        """

        # Get the underlying HttpRequest object
        request = request._request
        user = getattr(request, 'user', None)

        # Unauthenticated, CSRF validation not required
        if not user or not user.is_active or not user.is_superuser:
            return None

        #self.enforce_csrf(request)

        # CSRF passed with authenticated user
        return (user, None)


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
    response = Response({},
                        status=rest_framework.status.HTTP_404_NOT_FOUND,
                        )
    fixup_api_response(response)
    response = JsonResponse(data=response.data)
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
    response = exception_handler(exc, context)
    if not response:
        message = str(_('Internal Server Error'))
        detail = str(exc)
        data = {'detail': detail} if detail else {}
        set_rollback()
        response = Response(data,
                            status=rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR)
    return fixup_api_response(response)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


class NoMetaData(BaseMetadata):
    def determine_metadata(self, request, view):
        return None