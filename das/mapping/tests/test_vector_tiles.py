"""
Test vector tile functionality for SpatialFeature model.
"""

from unittest.mock import patch

import pytest

from django.core.cache import cache
from django.test import RequestFactory

from mapping.vector_layers import SpatialFeatureLayer
from mapping.views import SpatialFeatureTileView


class TestSpatialFeatureVectorTiles:
    """Test suite for SpatialFeature vector tiles."""

    def test_spatial_feature_layer_basic_config(self):
        """Test that the layer has correct basic configuration."""
        layer = SpatialFeatureLayer()

        assert layer.model.__name__ == "SpatialFeature"
        assert layer.id == "spatial_features"
        assert layer.geometry_field == "feature_geometry"
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24
        assert "id" in layer.tile_fields
        assert "name" in layer.tile_fields

    @pytest.mark.django_db
    def test_spatial_feature_layer_queryset(self):
        """Test that the layer correctly builds querysets."""
        layer = SpatialFeatureLayer()

        # Should work without errors
        queryset = layer.get_vector_tile_queryset(10, 100, 200)
        assert queryset is not None

        # Should include the annotated fields
        queryset_str = str(queryset.query)
        assert "feature_type_name" in queryset_str or "feature_type__name" in queryset_str

    def test_vector_tile_view_cache_hit(self):
        """Test that cache hit works correctly."""
        factory = RequestFactory()
        request = factory.get("/tiles/10/327/791.pbf")

        view = SpatialFeatureTileView()

        # Mock the parent get method to return a proper HttpResponse
        with patch.object(view.__class__.__bases__[0], "get") as mock_parent_get:
            from django.http import HttpResponse

            mock_response = HttpResponse(b"mock_tile_data", content_type="application/x-protobuf")
            mock_parent_get.return_value = mock_response

            # First call should generate tile and cache it
            response1 = view.get(request, 10, 327, 791)

            # Second call should hit cache
            response2 = view.get(request, 10, 327, 791)

            # Parent should only be called once (first time)
            assert mock_parent_get.call_count == 1
            # Both responses should have cache headers
            assert "Cache-Control" in response1
            assert "Cache-Control" in response2

    def test_vector_tile_view_cache_miss(self):
        """Test that cache miss generates new tile."""
        factory = RequestFactory()
        request = factory.get("/tiles/10/327/791.pbf")

        view = SpatialFeatureTileView()

        # Clear any existing cache
        cache.clear()

        # Mock the parent get method to return a proper HttpResponse
        with patch.object(view.__class__.__bases__[0], "get") as mock_parent_get:
            from django.http import HttpResponse

            mock_response = HttpResponse(b"mock_tile_data", content_type="application/x-protobuf")
            mock_parent_get.return_value = mock_response

            # Call should generate tile since cache is empty
            response = view.get(request, 10, 327, 791)

            # Parent should be called to generate tile
            assert mock_parent_get.call_count == 1
            assert "Cache-Control" in response

    def test_vector_tile_view_cache_headers(self):
        """Test that cache headers are set correctly."""
        factory = RequestFactory()
        request = factory.get("/tiles/10/327/791.pbf")

        view = SpatialFeatureTileView()

        # Clear any existing cache
        cache.clear()

        # Mock the parent get method to return a response with headers
        with patch.object(view.__class__.__bases__[0], "get") as mock_parent_get:
            # Create a mock response that behaves like HttpResponse
            from django.http import HttpResponse

            mock_response = HttpResponse(b"mock_tile_data", content_type="application/x-protobuf")
            mock_parent_get.return_value = mock_response

            # Call should generate tile and set cache headers
            response = view.get(request, 10, 327, 791)

            # Check that Cache-Control header is set for 1 hour
            assert "Cache-Control" in response
            assert response["Cache-Control"] == "public, max-age=3600"

            # Test cache hit also has headers
            response2 = view.get(request, 10, 327, 791)
            assert "Cache-Control" in response2
            assert response2["Cache-Control"] == "public, max-age=3600"


# Example of how to test the actual vector tile endpoint
@pytest.mark.django_db
class TestSpatialFeatureTileEndpoint:
    """Integration tests for the vector tile endpoint."""

    def test_tile_endpoint_accessibility(self):
        """Test that the tile endpoint is accessible."""
        factory = RequestFactory()

        # Create a request to the tile endpoint
        request = factory.get("/api/v1.0/mapping/tiles/10/512/512.pbf")

        view = SpatialFeatureTileView()
        view.setup(request)

        # This would require actual spatial data to test fully
        # For now, just ensure the view can be instantiated
        assert view.layer_classes == [SpatialFeatureLayer]

    def test_tile_view_basic_functionality(self):
        """Test basic tile view functionality."""
        factory = RequestFactory()

        # Create a simple request
        request = factory.get("/api/v1.0/mapping/tiles/10/512/512.pbf")

        view = SpatialFeatureTileView()
        view.setup(request)

        # Test that the view has the expected configuration
        assert len(view.layer_classes) == 1
        assert view.layer_classes[0] == SpatialFeatureLayer
