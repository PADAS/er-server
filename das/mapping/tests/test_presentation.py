import pytest

from django.contrib.gis.geos import Point
from django.urls import reverse

from mapping.models import DisplayCategory, SpatialFeature, SpatialFeatureType


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestPresentationFieldPriority:
    """
    GeoJSON responses for FeatureGeoJsonView and FeatureSetGeoJsonView flatten the
    resolved presentation onto the feature properties. A feature's own presentation
    JSON, when set, must take precedence over the feature type's presentation.
    """

    FEATURE_TYPE_PRESENTATION = {
        "image": "/static/ranger_post-black.svg",
        "width": 20,
        "height": 20,
    }
    # Same keys as FEATURE_TYPE_PRESENTATION but different values — lets us assert
    # that the override wins, not just that something is returned.
    PRESENTATION_OVERRIDE = {
        "image": "/static/custom-override.svg",
        "width": 50,
        "height": 50,
    }

    @pytest.fixture
    def category(self):
        return DisplayCategory.objects.create(name="Test Category")

    @pytest.fixture
    def feature_type_with_presentation(self, category):
        """Feature type whose presentation JSON is set."""
        return SpatialFeatureType.objects.create(
            name="Type With Presentation",
            display_category=category,
            presentation=self.FEATURE_TYPE_PRESENTATION,
        )

    @pytest.fixture
    def feature_type_without_presentation(self, category):
        """Feature type with no presentation JSON (empty dict)."""
        return SpatialFeatureType.objects.create(
            name="Type Without Presentation",
            display_category=category,
            presentation={},
        )

    @pytest.fixture
    def feature_with_presentation(self, feature_type_with_presentation):
        """Feature that overrides its type's presentation."""
        return SpatialFeature.objects.create(
            name="Feature With Presentation",
            feature_type=feature_type_with_presentation,
            presentation=self.PRESENTATION_OVERRIDE,
            feature_geometry=Point(-122.3, 47.5),
        )

    @pytest.fixture
    def feature_without_presentation(self, feature_type_with_presentation):
        """Feature with no own presentation — inherits from feature type."""
        return SpatialFeature.objects.create(
            name="Feature Without Presentation",
            feature_type=feature_type_with_presentation,
            feature_geometry=Point(-122.4, 47.6),
        )

    # --- FeatureGeoJsonView ---

    def test_feature_geojson_flattens_presentation_when_feature_overrides_type(
        self, user_client, feature_with_presentation
    ):
        url = reverse("mapping:mapping-feature-geojson", args=[feature_with_presentation.id.hex])
        response = user_client.get(url)
        assert response.status_code == 200

        props = response.json()["features"][0]["properties"]
        assert props["image"] == self.PRESENTATION_OVERRIDE["image"]
        assert props["width"] == self.PRESENTATION_OVERRIDE["width"]
        assert props["height"] == self.PRESENTATION_OVERRIDE["height"]
        # Resolved styling is flattened; clients should not see a nested object.
        assert "presentation" not in props
        assert "default_presentation" not in props

    def test_feature_geojson_falls_back_to_feature_type_presentation(self, user_client, feature_without_presentation):
        url = reverse("mapping:mapping-feature-geojson", args=[feature_without_presentation.id.hex])
        response = user_client.get(url)
        assert response.status_code == 200

        props = response.json()["features"][0]["properties"]
        assert props["image"] == self.FEATURE_TYPE_PRESENTATION["image"]
        assert props["width"] == self.FEATURE_TYPE_PRESENTATION["width"]
        assert props["height"] == self.FEATURE_TYPE_PRESENTATION["height"]
        assert "presentation" not in props

    # --- FeatureSetGeoJsonView ---

    def test_featureset_geojson_flattens_presentation_when_feature_overrides_type(
        self, user_client, feature_with_presentation, category
    ):
        url = reverse("mapping:mapping-featureset-geojson", kwargs={"id": str(category.id)})
        response = user_client.get(url)
        assert response.status_code == 200

        features = response.json()["features"]
        assert len(features) == 1
        props = features[0]["properties"]
        assert props["image"] == self.PRESENTATION_OVERRIDE["image"]
        assert props["width"] == self.PRESENTATION_OVERRIDE["width"]
        assert props["height"] == self.PRESENTATION_OVERRIDE["height"]
        assert "presentation" not in props

    def test_featureset_geojson_falls_back_to_feature_type_presentation(
        self, user_client, feature_without_presentation, category
    ):
        url = reverse("mapping:mapping-featureset-geojson", kwargs={"id": str(category.id)})
        response = user_client.get(url)
        assert response.status_code == 200

        features = response.json()["features"]
        assert len(features) == 1
        props = features[0]["properties"]
        assert props["image"] == self.FEATURE_TYPE_PRESENTATION["image"]
        assert props["width"] == self.FEATURE_TYPE_PRESENTATION["width"]
        assert props["height"] == self.FEATURE_TYPE_PRESENTATION["height"]
        assert "presentation" not in props

    def test_featureset_geojson_resolves_each_feature_independently(
        self, user_client, feature_with_presentation, feature_without_presentation, category
    ):
        """Both features in the same featureset use the correct source for their resolved styling."""
        url = reverse("mapping:mapping-featureset-geojson", kwargs={"id": str(category.id)})
        response = user_client.get(url)
        assert response.status_code == 200

        by_name = {f["properties"]["title"]: f["properties"] for f in response.json()["features"]}
        assert by_name["Feature With Presentation"]["image"] == self.PRESENTATION_OVERRIDE["image"]
        assert by_name["Feature Without Presentation"]["image"] == self.FEATURE_TYPE_PRESENTATION["image"]
