"""
Etag generation in views by extending DRF's built-in pipeline for filtering, pagination, get_object, etc.
No code duplication, no weird extraction of queryset generation logic, no second instance, no confusion.
"""

from typing import Optional

from django.db import models
from django.utils.cache import get_conditional_response
from django.utils.http import http_date, quote_etag
from rest_framework.request import Request
from rest_framework.response import Response

from utils.etags import get_hash_from_model_instance, get_hash_from_queryset


def uses_modified_since_headers(request: Request) -> bool:
    """
    Returns True if the request includes either 'If-Modified-Since' or 'If-Unmodified-Since'
    headers for conditional requests.
    """
    meta_keys = request._request.META.keys()
    return "HTTP_IF_UNMODIFIED_SINCE" in meta_keys or "HTTP_IF_MODIFIED_SINCE" in meta_keys


def add_response_headers(response: Response, etag: str, last_modified: Optional[str]) -> Response:
    """
    Appends ETag and Last-Modified headers to the given Response (if last_modified is provided).
    """
    response.headers["ETag"] = etag
    if last_modified is not None:
        response.headers["Last-Modified"] = http_date(last_modified)
    return response


class EtagListModelMixin:
    """
    Provides ETag and Last-Modified logic for 'list' actions.

    Subclasses can set 'last_modified_field' to a field name (e.g. 'updated_at')
    for 'If-Modified-Since' support.
    """

    last_modified_field = None

    def get_list_last_modified(self, queryset: models.QuerySet) -> Optional[str]:
        """Hook to return the last modified time of the queryset."""
        if self.last_modified_field is None:
            return None
        try:
            latest = queryset.latest(self.last_modified_field)
            return getattr(latest, self.last_modified_field)
        except queryset.model.DoesNotExist:
            return None

    def get_list_etag(self, request: Request, queryset: models.QuerySet) -> str:
        """
        By default, this method will compute a hash of the etire queryset.

        Override for custom ETag generation.
        """
        return get_hash_from_queryset(queryset, request)

    def list(self, request: Request, *args, **kwargs) -> Response:
        """List a queryset, with etag and last-modified support."""
        queryset = self.filter_queryset(self.get_queryset())
        # page is a queryset if pagination is applied, None otherwise
        page = self.paginate_queryset(queryset)

        last_modified = None
        if uses_modified_since_headers(request):
            last_modified = self.get_list_last_modified(queryset)

        etag = quote_etag(self.get_list_etag(request, queryset))

        # response is None if the request is not conditional, short-circuit to 304.
        response = get_conditional_response(request, etag, last_modified)
        if response is None:
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                response = self.get_paginated_response(serializer.data)
            else:
                serializer = self.get_serializer(queryset, many=True)
                response = Response(serializer.data)

        return add_response_headers(response, etag, last_modified)


class EtagRetrieveModelMixin:
    """
    Provides ETag and Last-Modified logic for 'retrieve' actions.

    Subclasses can set 'last_modified_field' to a model field name (e.g. 'updated_at')
    for 'If-Modified-Since' support.
    """

    last_modified_field = None

    def get_object_last_modified(self, obj: models.Model) -> Optional[str]:
        """Hook to retrieve the last modified value of the object."""
        if not self.last_modified_field:
            return None
        return getattr(obj, self.last_modified_field)

    def get_object_etag(self, request: Request, obj: models.Model) -> str:
        """
        By default, this method will compute a hash of the object.
        """
        return get_hash_from_model_instance(obj, request)

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()

        last_modified = None
        if uses_modified_since_headers(request):
            last_modified = self.get_object_last_modified(instance)

        etag = quote_etag(self.get_object_etag(request, instance))

        response = get_conditional_response(request, etag, last_modified)
        if response is None:
            serializer = self.get_serializer(instance)
            response = Response(serializer.data)

        return add_response_headers(response, etag, last_modified)


class EtagListRetrieveModelMixin(EtagListModelMixin, EtagRetrieveModelMixin):
    """
    Provides ETag and Last-Modified logic for both 'list' and 'retrieve' actions.

    Subclasses can set 'last_modified_field' to a model field name (e.g. 'updated_at')
    for 'If-Modified-Since' support.
    """
