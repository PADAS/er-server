from vectortiles import VectorLayer

from django.db.models import F

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature


class SpatialFeatureLayer(VectorLayer):
    model = SpatialFeature
    id = "spatial_features"
    geometry_field = "feature_geometry"  # Use the transformed geometry field
    tile_fields = (
        "id",
        "name",
        "short_name",
        "external_id",
        "description",
        "feature_type_id",
        "feature_type_name",
        "display_category_name",
        "presentation",
        "attributes",
        "image",
    )
    min_zoom = 3
    max_zoom = 24
    filterset_class = SpatialFeatureFilterSet

    def get_vector_tile_queryset(self, zoom, x, y):
        from django.contrib.gis.db import models as gis_models
        from django.contrib.gis.db.models.functions import Transform
        from django.db.models import Case, CharField, Value, When
        from django.db.models.functions import Cast

        return self.model.objects.select_related("feature_type", "feature_type__display_category").annotate(
            feature_type_name=F("feature_type__name"),
            display_category_name=F("feature_type__display_category__name"),
            # Cast geography to geometry, then transform to Web Mercator for django-vectortiles compatibility
            geom=Transform(Cast(F("feature_geometry"), gis_models.GeometryField()), 3857),
            # Extract image from presentation data - prioritize feature-level image, then fall back to feature_type
            image=Case(
                When(presentation__has_key="image", then=F("presentation__image")),
                When(feature_type__presentation__has_key="image", then=F("feature_type__presentation__image")),
                default=Value(None),
                output_field=CharField(),
            ),
        )

    def get_tile(self, x, y, z):
        """Override to ensure proper geometry field handling"""
        # The parent class may not be using our geometry_field correctly
        # Let's check if we need to alias the geometry field
        queryset = self.get_vector_tile_queryset(z, x, y)

        # If the library expects 'geom' but we have 'feature_geometry',
        # we need to alias it
        if self.geometry_field != "geom":
            queryset = queryset.annotate(geom=F(self.geometry_field))

        return super().get_tile(x, y, z)
