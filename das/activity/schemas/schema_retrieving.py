import logging
from functools import partial
from urllib.parse import urlparse

from referencing import Registry, Resource
from referencing import exceptions as referencing_exceptions
from referencing.jsonschema import DRAFT202012

from django.http import QueryDict
from django.urls import Resolver404, resolve
from rest_framework.request import Request as DRFRequest
from rest_framework.request import clone_request

from activity.exceptions import UriIsNotJsonSchema, UriNotFound
from schemas.view_mixins import DynamicSchemaFromSourceView

logger = logging.getLogger(__name__)


class TemporaryRequestUrl:
    """
    A context manager that temporarily overrides the URL on a request,
    additionally setting the `view.request` attribute.

    Usage:
        with TemporaryRequestUrl(request, path, query_params) as request:
            ... # Do stuff with `request`
    """

    def __init__(self, request: DRFRequest, path: str, query_params: str = ""):
        self.request = request
        self.original_path = request._request.path
        self.original_path_info = request._request.path_info
        self.original_query_params = request._request.META["QUERY_STRING"]
        self.path = path
        self.query_params = query_params

    def __enter__(self):
        request = clone_request(self.request, method="GET")
        request._request.path = self.path
        request._request.path_info = self.path
        request._request.META["QUERY_STRING"] = self.query_params
        request._request.GET = QueryDict(self.query_params, mutable=True)
        return request

    def __exit__(self, *args, **kwarg):
        self.request._request.path = self.original_path
        self.request._request.path_info = self.original_path_info
        self.request._request.META["QUERY_STRING"] = self.original_query_params
        self.request._request.GET = QueryDict(self.original_query_params, mutable=True)


def retrieve_dynamic_schema(uri: str, request: DRFRequest) -> Resource:
    """
    Retrieve a JSON schema from an internal dynamic schema view by reusing its generate_dynamic_schema method.

    If any step fails (e.g., the URI cannot be resolved or the view is not a dynamic schema view),
    an Unresolvable exception is raised.
    """
    # Parse the URI and extract the path (domain agnostic)...
    parsed = urlparse(uri)
    try:
        match = resolve(parsed.path)
    except Resolver404 as e:
        logger.info("URI %s cannot be resolved to an internal view: %s", uri, e)
        raise UriNotFound(message="URI cannot be resolved to an internal view", uri=uri) from e

    # Let's verify that it's a DynamicSchemaFromSourceView
    # Note: Instead of checking that it's a subclass of DynamicSchemaFromSourceView,
    # we can check something more generic, like just something that has a `generate_schema` method
    view_class = getattr(match.func, "view_class", None)
    if not view_class or not issubclass(view_class, DynamicSchemaFromSourceView):
        logger.info("Resolved view for URI %s is not a DynamicSchemaFromSourceView.", uri)
        raise UriIsNotJsonSchema(message="Resolved view for URI is not a DynamicSchemaFromSourceView", uri=uri)

    view_instance = view_class(**match.kwargs)

    with TemporaryRequestUrl(request, parsed.path, parsed.query) as cloned_request:
        try:
            schema = view_instance.generate_dynamic_schema(request=cloned_request)
        except Exception as e:
            logger.warning("Error rendering schema for URI %s: %s", uri, e)
            raise referencing_exceptions.Unresolvable(ref=uri) from e

    return Resource.from_contents(contents=schema, default_specification=DRAFT202012)


def build_dynamic_schemas_registry(request: DRFRequest) -> Registry:
    """
    Connects the request to the dynamic schema retriever, so that it can use the request to resolve dynamic schemas.
    """
    # Future: we can implement a list of retrievers that can have a `can_handle(uri)` or `can_resolve(uri)` method
    # to determine which retriever to use for a given URI.
    with_request_retriever = partial(retrieve_dynamic_schema, request=request)
    return Registry(retrieve=with_request_retriever)
