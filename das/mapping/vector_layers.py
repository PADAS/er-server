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
        from django.contrib.gis.db.models.functions import Transform

        return self.model.objects.select_related("feature_type", "feature_type__display_category").annotate(
            feature_type_name=F("feature_type__name"),
            display_category_name=F("feature_type__display_category__name"),
            # Convert geography to geometry in Web Mercator for django-vectortiles compatibility
            geom=Transform(self.geometry_field, 3857),
        )
