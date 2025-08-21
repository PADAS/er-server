"""
Test vector tile functionality for SpatialFeature model.
"""

from unittest.mock import patch

import pytest

from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import RequestFactory

from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType
from mapping.vector_layers import SpatialFeatureLayer
from mapping.views import SpatialFeatureTileView


class TestSpatialFeatureVectorTiles:
    """Test suite for SpatialFeature vector tiles."""

    def test_spatial_feature_layer_basic_config(self):
        """Test that the layer has correct basic configuration."""
        layer = SpatialFeatureLayer()

        assert layer.model.__name__ == "SpatialFeature"
        assert layer.id == "spatial_features"
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
        request.META["HTTP_AUTHORIZATION"] = "Bearer testtoken1"

        view = SpatialFeatureTileView()

        with patch.object(view.__class__.__bases__[0], "get") as mock_parent_get:
            from django.http import HttpResponse

            mock_response = HttpResponse(b"mock_tile_data", content_type="application/x-protobuf")
            mock_parent_get.return_value = mock_response

            response1 = view.get(request, 10, 327, 791)
            response2 = view.get(request, 10, 327, 791)

            assert mock_parent_get.call_count == 1
            assert "Cache-Control" in response1
            assert "Cache-Control" in response2

    def test_vector_tile_view_cache_miss(self):
        """Test that cache miss generates new tile."""
        factory = RequestFactory()
        request = factory.get("/tiles/10/327/791.pbf")
        request.META["HTTP_AUTHORIZATION"] = "Bearer testtoken2"

        view = SpatialFeatureTileView()
        cache.clear()

        with patch.object(view.__class__.__bases__[0], "get") as mock_parent_get:
            from django.http import HttpResponse

            mock_response = HttpResponse(b"mock_tile_data", content_type="application/x-protobuf")
            mock_parent_get.return_value = mock_response

            response = view.get(request, 10, 327, 791)
            assert mock_parent_get.call_count == 1
            assert "Cache-Control" in response

    def test_vector_tile_view_cache_headers(self):
        """Test that cache headers are set correctly."""
        factory = RequestFactory()
        request = factory.get("/tiles/10/327/791.pbf")
        request.META["HTTP_AUTHORIZATION"] = "Bearer testtoken3"

        view = SpatialFeatureTileView()
        cache.clear()

        with patch.object(view.__class__.__bases__[0], "get") as mock_parent_get:
            from django.http import HttpResponse

            mock_response = HttpResponse(b"mock_tile_data", content_type="application/x-protobuf")
            mock_parent_get.return_value = mock_response

            response = view.get(request, 10, 327, 791)
            assert "Cache-Control" in response
            cc = response["Cache-Control"]
            assert "max-age=86400" in cc
            assert "stale-while-revalidate=86400" in cc
            assert "stale-if-error=86400" in cc

            response2 = view.get(request, 10, 327, 791)
            assert "Cache-Control" in response2
            cc2 = response2["Cache-Control"]
            assert "max-age=86400" in cc2
            assert "stale-while-revalidate=86400" in cc2
            assert "stale-if-error=86400" in cc2

    @pytest.mark.django_db
    def test_image_annotation_precedence(self, django_assert_num_queries):
        """Verify that image annotation resolves through image -> icon_url -> feature_type fallbacks."""
        # Create feature type with icon_url only
        dc = DisplayCategory.objects.create(name="General")
        ft = SpatialFeatureType.objects.create(
            name="Camp",
            presentation={"icon_url": "type_icon.png"},
            display_category=dc,
        )
        # Feature 1: has explicit image
        f1 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Feat1",
            presentation={"image": "feat_image.png"},
            feature_geometry=Point(0, 0),
        )
        # Feature 2: has icon_url only
        f2 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Feat2",
            presentation={"icon_url": "feat_icon.png"},
            feature_geometry=Point(1, 1),
        )
        # Feature 3: no image fields; should inherit feature_type icon_url
        f3 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Feat3",
            presentation={},
            feature_geometry=Point(2, 2),
        )
        # Feature 4: nested image dict pattern
        f4 = SpatialFeature.objects.create(
            feature_type=ft,
            name="Feat4",
            presentation={"image": {"image": "nested_image.png", "width": 20, "height": 20}},
            feature_geometry=Point(3, 3),
        )

        layer = SpatialFeatureLayer()
        qs = layer.get_vector_tile_queryset(10, 0, 0).filter(id__in=[f1.id, f2.id, f3.id, f4.id])
        assert qs.count() == 4
        results = {r.id: r.image for r in qs}

        assert results[f1.id] == "feat_image.png"
        assert results[f2.id] == "feat_icon.png"
        assert results[f3.id] == "type_icon.png"
        assert results[f4.id] == "nested_image.png"


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
