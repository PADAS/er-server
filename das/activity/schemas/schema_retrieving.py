import logging
from urllib.parse import urlparse

from referencing import Registry, Resource
from referencing import exceptions as referencing_exceptions
from referencing.jsonschema import DRAFT202012
from referencing.typing import URI

from django.test import RequestFactory
from django.urls import Resolver404, resolve
from rest_framework.request import Request as DRFRequest

from schemas.view_mixins import DynamicSchemaFromSourceView

logger = logging.getLogger(__name__)


def dynamic_schemas_retriever(uri: str) -> Resource:
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
    try:
        # Parse the URI and extract the path (domain agnostic)...
        parsed = urlparse(uri)
        path = parsed.path

        match = resolve(path)
    except Resolver404 as e:
        logger.info(f"URI {uri} cannot be resolved to an internal view: {e}")
        raise referencing_exceptions.Unresolvable(ref=uri)

    # Let's verify that it's a DynamicSchemaFromSourceView.
    view_class = getattr(match.func, "view_class", None)
    if not view_class or not issubclass(view_class, DynamicSchemaFromSourceView):
        logger.info(f"Resolved view for URI {uri} is not a DynamicSchemaFromSourceView.")
        raise referencing_exceptions.Unresolvable(ref=uri)

    # Create a dummy GET request for the URI.
    factory = RequestFactory()
    http_request = factory.get(uri)
    drf_request = DRFRequest(http_request)

    view_instance = view_class(**match.kwargs)
    view_instance.request = drf_request

    try:
        schema_data = view_instance.render_schema(drf_request)
    except Exception as e:
        logger.warning(f"Error rendering schema for URI {uri}: {e}")
        raise referencing_exceptions.Unresolvable(ref=uri)

    resource = Resource.from_contents(contents=schema_data, default_specification=DRAFT202012)
    return resource


def build_dynamic_schemas_registry(base_url: str) -> Registry:
    """
    Wrapper function to build a Registry with a dynamic schema retriever for internal views.
    """
    registry = Registry(retrieve=dynamic_schemas_retriever)
    return registry


def get_local_memory_retriever(base_url: str, local_schemas: dict) -> callable:

    def in_memory_retriever(uri: URI) -> Resource:
        print(f"Retrieving schema {uri}")
        if uri.startswith(base_url):
            local_uri = uri[len(base_url) :]
            local_uri = local_uri.lstrip("/")
            if local_uri in local_schemas:
                schema = Resource.from_contents(
                    contents=local_schemas[local_uri],
                    default_specification=DRAFT202012,
                )
                return schema
            else:
                print(f"Schema {uri} not found in local schemas")
                raise referencing_exceptions.NoSuchResource(ref=uri)
        print(f"Schema {uri} should be retrieved from the internet")
        raise referencing_exceptions.Unresolvable(ref=uri)

    return in_memory_retriever
