import logging

from vectortiles import VectorLayer

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import Transform
from django.db.models import Case, CharField, F, Value, When
from django.db.models.expressions import RawSQL
from django.db.models.functions import Cast

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature

logger = logging.getLogger(__name__)


class SpatialFeatureLayer(VectorLayer):
    model = SpatialFeature
    # NOTE: Do NOT set a class-level queryset. We build it per request in get_queryset()
    # to avoid stale / tenant-mismatched data and to allow filterset logic to start
    # from a fresh base each time.

    id = "spatial_features"
    tile_fields = (
        "name",
        "int_id",
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

    def get_queryset(self):  # invoked by django-vectortiles when building tiles
        """Return a fresh annotated queryset each request.

        Builds annotations needed inside the vector tiles:
        - int_id: stable hashed integer id (smaller than UUID in tile payload)
        - feature_type/display category names for styling / filtering client-side
        - geom: geometry transformed to Web Mercator (SRID 3857) from geography
        - image: presentation-derived image with feature-level override

        Returning a new queryset each call avoids shared state issues that caused
        intermittent empty (204) tiles when a class-level queryset became stale.
        """
        qs = (
            self.model.objects.select_related("feature_type", "feature_type__display_category")
            .filter(feature_type__display_category__isnull=False)
            .annotate(
                int_id=RawSQL("hashtext(CAST(mapping_spatialfeature.id AS TEXT))", []),
                feature_type_name=F("feature_type__name"),
                display_category_name=F("feature_type__display_category__name"),
                # Cast geography to geometry then transform to 3857 for django-vectortiles
                geom=Transform(Cast(F("feature_geometry"), gis_models.GeometryField()), 3857),
                image=Case(
                    When(presentation__has_key="image", then=F("presentation__image")),
                    When(
                        feature_type__presentation__has_key="image",
                        then=F("feature_type__presentation__image"),
                    ),
                    default=Value(None),
                    output_field=CharField(),
                ),
            )
        )
        # Lightweight debug logging (safe; only logs count, not evaluating full queryset)
        try:
            cnt = qs.count()
            logger.debug("SpatialFeatureLayer queryset count=%s", cnt)
        except Exception:  # pragma: no cover - defensive logging only
            logger.debug("SpatialFeatureLayer queryset count unavailable (lazy evaluation error)")
        return qs
