from unittest.mock import Mock

import pytest
from referencing import Resource
from referencing import exceptions as referencing_exceptions

from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.schemas.schema_retrieving import (
    _dynamic_schemas_retriever,
    build_dynamic_schemas_registry,
)
from schemas.tests.fixtures import TestDynamicSchemaView


@pytest.mark.django_db
class TestDynamicSchemaRetriever:
    def setup_method(self):
        self.mock_request = Mock(spec=Request)

    def test_successful_schema_retrieval(self, add_view_to_urls, superuser_client):
        # Setup - add the test view to URLs
        add_view_to_urls(TestDynamicSchemaView, route="test-schema/", name="test-schema")
        url = reverse("tests:test-schema")

        # Execute
        result = _dynamic_schemas_retriever(url, superuser_client.request)

        # Assert
        assert isinstance(result, Resource)
        schema_contents = result.contents
        assert "oneOf" in schema_contents
        items = schema_contents["oneOf"]
        assert len(items) == 2
        assert items[0]["const"] == "uuid1"
        assert items[0]["title"] == "John Doe"
        assert items[0]["description"] == "A person"

    def test_unresolvable_uri(self):
        # Execute & Assert
        with pytest.raises(referencing_exceptions.Unresolvable):
            _dynamic_schemas_retriever("/non-existent-path/", self.mock_request)

    def test_non_dynamic_schema_view(self, add_view_to_urls):
        # Setup - create a regular view that's not a DynamicSchemaFromSourceView
        class RegularView(APIView):
            def get(self, request):
                return Response({})

        add_view_to_urls(RegularView, route="regular-view/", name="regular-view")
        url = reverse("tests:regular-view")

        # Execute & Assert
        with pytest.raises(referencing_exceptions.Unresolvable):
            _dynamic_schemas_retriever(url, self.mock_request)

    def test_view_rendering_error(self, add_view_to_urls):
        # Setup - create a view that raises an error
        class ErrorView(TestDynamicSchemaView):
            def render_schema(self, request):
                raise ValueError("Rendering failed")

        add_view_to_urls(ErrorView, route="error-view/", name="error-view")
        url = reverse("tests:error-view")

        # Execute & Assert
        with pytest.raises(referencing_exceptions.Unresolvable):
            _dynamic_schemas_retriever(url, self.mock_request)

    def test_uri_with_query_params(self, add_view_to_urls):
        # Setup
        add_view_to_urls(TestDynamicSchemaView, route="test-schema/", name="test-schema")
        base_url = reverse("tests:test-schema")
        url_with_params = f"{base_url}?mode=full&version=2"

        # Execute
        result = _dynamic_schemas_retriever(url_with_params, self.mock_request)

        # Assert
        assert isinstance(result, Resource)
        schema_contents = result.contents
        assert "oneOf" in schema_contents

    def test_build_dynamic_schemas_registry(self):
        mock_request = Mock(spec=Request)
        registry = build_dynamic_schemas_registry(mock_request)

        assert registry is not None
        assert callable(registry.retrieve)
        retrieve_func = registry.retrieve
        assert retrieve_func.func == _dynamic_schemas_retriever
        assert retrieve_func.keywords == {"request": mock_request}
