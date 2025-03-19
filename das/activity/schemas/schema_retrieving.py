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

from schemas.view_mixins import DynamicSchemaFromSourceView

logger = logging.getLogger(__name__)


def clone_request_with_url(original_request: DRFRequest, path: str, query_params: str = "") -> DRFRequest:
    """
    Creates a new DRF Request from `original_request`, but updates the path
    and query parameters to match `url`.
    """
    cloned = clone_request(original_request, method=original_request.method)

    # Overwrite path, path_info, and query string
    cloned._request.path = path
    cloned._request.path_info = path
    cloned._request.META["QUERY_STRING"] = query_params
    cloned._request.GET = QueryDict(query_params, mutable=True)

    return cloned


def dynamic_schemas_retriever(uri: str, request: DRFRequest) -> Resource:
    """
    Retrieve a JSON schema from an internal dynamic schema view by reusing its render_schema method.

    This implementation:
      - Parses and resolves the URI to find a corresponding view.
      - Checks that the resolved view is a subclass of DynamicSchemaFromSourceView.
      - Creates a dummy GET request and assigns it to an instance of the view.
      - Calls the view's render_schema method to obtain the schema dictionary.
      - Wraps the schema in a Resource object.

    If any step fails (e.g., the URI cannot be resolved or the view is not a dynamic schema view),
    an Unresolvable exception is raised.
    """
    # Parse the URI and extract the path (domain agnostic)...
    parsed = urlparse(uri)
    try:
        match = resolve(parsed.path)
    except Resolver404 as e:
        logger.info(f"URI {uri} cannot be resolved to an internal view: {e}")
        raise referencing_exceptions.Unresolvable(ref=uri)

    # Let's verify that it's a DynamicSchemaFromSourceView
    # Note: Instead of checking that it's a subclass of DynamicSchemaFromSourceView,
    # we can check something more friendly like the existence of a render_schema method.
    view_class = getattr(match.func, "view_class", None)
    if not view_class or not issubclass(view_class, DynamicSchemaFromSourceView):
        logger.info(f"Resolved view for URI {uri} is not a DynamicSchemaFromSourceView.")
        raise referencing_exceptions.Unresolvable(ref=uri)

    view_instance = view_class(**match.kwargs)

    try:
        schema_data = view_instance.render_schema(request=clone_request_with_url(request, parsed.path, parsed.query))
        # TODO: each clone request is mutating the underlying request object, we should fix that
    except Exception as e:
        logger.warning(f"Error rendering schema for URI {uri}: {e}")
        raise referencing_exceptions.Unresolvable(ref=uri)

    resource = Resource.from_contents(contents=schema_data, default_specification=DRAFT202012)
    return resource


def build_dynamic_schemas_registry(request: DRFRequest) -> Registry:
    """
    Wrapper function to build a Registry with a dynamic schema retriever for internal views.
    """
    # Future: we can implement a list of retrievers that can have a `can_handle(uri)` or `can_resolve(uri)` method
    # to determine which retriever to use for a given URI.
    uri_only_retriever = partial(dynamic_schemas_retriever, request=request)
    return Registry(retrieve=uri_only_retriever)
