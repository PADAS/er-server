from vectortiles import VectorLayer

from django.db.models import F

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature


class SpatialFeatureLayer(VectorLayer):
    model = SpatialFeature
    id = "spatial_features"
    geometry_field = "geom"  # Use the transformed geometry field
    tile_fields = (
        "id",
        "name",
        "short_name",
        "external_id",
        "external_source",
        "description",
        "feature_type_id",
        "feature_type_name",
        "display_category_name",
        "presentation",
        "attributes",
    )
    min_zoom = 3
    max_zoom = 24
    filterset_class = SpatialFeatureFilterSet

    def get_vector_tile_queryset(self, zoom, x, y):
        from django.contrib.gis.db import models as gis_models
        from django.contrib.gis.db.models.functions import Transform
        from django.db.models.functions import Cast

        return self.model.objects.select_related("feature_type", "feature_type__display_category").annotate(
            feature_type_name=F("feature_type__name"),
            display_category_name=F("feature_type__display_category__name"),
            # Cast geography to geometry, then transform to Web Mercator for django-vectortiles compatibility
            geom=Transform(Cast(F("feature_geometry"), gis_models.GeometryField()), 3857),
        )
