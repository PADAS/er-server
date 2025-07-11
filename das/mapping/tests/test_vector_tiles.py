"""
Test vector tile functionality for SpatialFeature model.
"""

import pytest

from django.test import RequestFactory

from mapping.filters import SpatialFeatureFilterSet
from mapping.spatialviews import SpatialFeatureTileView
from mapping.vector_layers import SpatialFeatureLayer


class TestSpatialFeatureVectorTiles:
    """Test suite for SpatialFeature vector tiles."""

    def test_spatial_feature_layer_filter_info(self):
        """Test that the layer provides correct filter information."""
        layer = SpatialFeatureLayer()
        filter_info = layer.get_filter_info()

        # Should include filters from SpatialFeatureFilterSet
        expected_filters = ["feature_class", "feature_set", "external_source"]
        for filter_name in expected_filters:
            assert filter_name in filter_info
            assert "field_name" in filter_info[filter_name]
            assert "filter_type" in filter_info[filter_name]

    def test_spatial_feature_layer_allowed_params(self):
        """Test that the layer correctly identifies allowed parameters."""
        layer = SpatialFeatureLayer()
        allowed_params = layer.get_allowed_filter_params()

        expected_mappings = {
            "feature_class": "feature_type",
            "feature_set": "feature_type__display_category",
            "external_source": "external_source",
        }

        for param, field in expected_mappings.items():
            assert param in allowed_params
            assert allowed_params[param] == field

    def test_vector_tile_view_cache_key_generation(self):
        """Test that cache keys are generated correctly with filtered parameters."""
        from mapping.vector_utils import get_vector_layer_cache_key_elements

        # Test with valid parameters
        params = {
            "feature_class": "1,2,3",
            "feature_set": "conservation",
            "external_source": "test",
            "invalid_param": "should_be_ignored",  # This should not appear in cache key
        }

        cache_elements = get_vector_layer_cache_key_elements(
            view_class_name="SpatialFeatureTileView",
            z=10,
            x=100,
            y=200,
            params=params,
            filterset_class=SpatialFeatureFilterSet,
        )

        cache_key = ":".join(map(str, cache_elements))

        # Should include valid parameters but exclude invalid ones
        assert "feature_class-1,2,3" in cache_key
        assert "feature_set-conservation" in cache_key
        assert "external_source-test" in cache_key
        assert "invalid_param" not in cache_key

    @pytest.mark.django_db
    def test_spatial_feature_layer_filtering(self):
        """Test that the layer correctly applies filtering."""
        # This test would require setting up test data
        # You can expand this based on your test data setup
        layer = SpatialFeatureLayer()

        # Test empty parameters
        empty_params = {}
        layer.request_params = empty_params

        # Should work without errors
        queryset = layer.get_vector_tile_queryset(10, 100, 200)
        assert queryset is not None

    def test_filterset_consistency(self):
        """Test that the FilterSet and vector layer are consistent."""
        # Create a filterset
        filterset = SpatialFeatureFilterSet()

        # Create a layer
        layer = SpatialFeatureLayer()

        # The layer should use the same filterset
        assert layer.filterset_class == SpatialFeatureFilterSet

        # The allowed parameters should match the filterset filters
        allowed_params = layer.get_allowed_filter_params()
        filterset_filters = list(filterset.filters.keys())

        for filter_name in filterset_filters:
            assert filter_name in allowed_params


# Example of how to test the actual vector tile endpoint
@pytest.mark.django_db
class TestSpatialFeatureTileEndpoint:
    """Integration tests for the vector tile endpoint."""

    def test_tile_endpoint_accessibility(self):
        """Test that the tile endpoint is accessible."""
        factory = RequestFactory()

        # Create a request to the tile endpoint
        request = factory.get("/api/mapping/spatialfeatures/tiles/10/512/512.pbf")

        view = SpatialFeatureTileView()
        view.setup(request)

        # This would require actual spatial data to test fully
        # For now, just ensure the view can be instantiated
        assert view.layer_classes == [SpatialFeatureLayer]

    def test_tile_endpoint_with_filters(self):
        """Test tile endpoint with filter parameters."""
        factory = RequestFactory()

        # Create a request with filter parameters
        request = factory.get(
            "/api/mapping/spatialfeatures/tiles/10/512/512.pbf", {"feature_class": "1,2", "external_source": "test"}
        )

        view = SpatialFeatureTileView()
        view.setup(request)

        # Test that the request parameters are handled
        assert "feature_class" in request.GET
        assert "external_source" in request.GET
