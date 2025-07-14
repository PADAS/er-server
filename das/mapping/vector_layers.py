from vectortiles import VectorLayer

from django.db.models import F

from mapping.models import SpatialFeature


class SpatialFeatureLayer(VectorLayer):
    model = SpatialFeature
    id = "spatial_features"
    geometry_field = "feature_geometry"
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

    def get_vector_tile_queryset(self, zoom, x, y):
        return self.model.objects.select_related("feature_type", "feature_type__display_category").annotate(
            feature_type_name=F("feature_type__name"),
            display_category_name=F("feature_type__display_category__name"),
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
