import pytest
from referencing import Registry, Resource
from referencing import exceptions as referencing_exceptions

from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from activity.schemas.schema_retrieving import (
    build_dynamic_schemas_registry,
    retrieve_dynamic_schema,
)
from schemas.tests.fixtures import MockDynamicSchemaView
from schemas.view_mixins import ENUM_EXTRA_KEY, DynamicSchemaFromSourceView


@pytest.mark.django_db
class TestDynamicSchemaRetriever:
    @pytest.fixture
    def api_request(self, superuser_client):
        # Create a proper DRF Request object
        django_request = APIRequestFactory().get("/")
        django_request.user = superuser_client.user
        return Request(django_request)

    def test_successful_schema_retrieval(self, add_view_to_urls, api_request):
        # Setup - add the test view to URLs
        url_name = add_view_to_urls(MockDynamicSchemaView)
        url = reverse(url_name)

        result = retrieve_dynamic_schema(url, api_request)
        assert isinstance(result, Resource)

        # Check some expected content in the schema
        enum_vals = result.contents.get("enum", [])
        extra = result.contents.get(ENUM_EXTRA_KEY, {})
        assert len(enum_vals) >= 2

        assert enum_vals[0] == "uuid1"
        assert extra["uuid1"]["display"] == "John Doe"
        assert extra["uuid1"]["description"] == "A person"

        assert enum_vals[1] == "uuid2"
        assert extra["uuid2"]["display"] == "Brigitte Bardot"
        assert extra["uuid2"]["description"] == "Actress and singer"

    def test_unresolvable_uri(self, api_request):
        # Execute & Assert
        with pytest.raises(referencing_exceptions.Unresolvable):
            retrieve_dynamic_schema("/non-existent-path/", api_request)

    def test_non_dynamic_schema_view(self, add_view_to_urls, api_request):
        # Create a regular view (not a DynamicSchemaFromSourceView)
        class NonDynamicView(APIView):
            def get(self, *args, **kwargs):
                return Response({"message": "This is not a schema view"})

        # Register the non-dynamic view using the fixture
        url_name = add_view_to_urls(NonDynamicView)
        url = reverse(url_name)
        # Execute & Assert
        with pytest.raises(referencing_exceptions.Unresolvable):
            retrieve_dynamic_schema(url, api_request)

    def test_view_rendering_error(self, add_view_to_urls, api_request):
        # Create a view that raises an exception when generating a schema
        class ErrorSchemaView(DynamicSchemaFromSourceView):
            def generate_dynamic_schema(self, request):
                raise ValueError("Rendering failed")

        url_name = add_view_to_urls(ErrorSchemaView)
        url = reverse(url_name)

        with pytest.raises(referencing_exceptions.Unresolvable):
            retrieve_dynamic_schema(url, api_request)

    def test_uri_with_query_params(self, add_view_to_urls, api_request):
        # Setup - The improved fixture returns the namespaced URL name
        url_name = add_view_to_urls(MockDynamicSchemaView, route="test-schema/", name="test-schema")
        base_url = reverse(url_name)
        url_with_params = f"{base_url}?s_value=custom_id"

        result = retrieve_dynamic_schema(url_with_params, api_request)

        assert isinstance(result, Resource)

        enum_vals = result.contents.get("enum", [])
        assert len(enum_vals) >= 2

        assert enum_vals[0] == "custom_uuid1"
        assert enum_vals[1] == "custom_uuid2"

    def test_build_dynamic_schemas_registry(self, api_request):
        registry = build_dynamic_schemas_registry(api_request)

        assert registry is not None
        assert isinstance(registry, Registry)
