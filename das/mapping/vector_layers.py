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
    id = "spatial_features"
    # Include 'id' so clients can still correlate (even though int_id provided)
    tile_fields = (
        "id",
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

    def _build_base_queryset(self):
        """Construct annotated queryset (called per access via queryset property).
        We deliberately DO NOT cache this on the class to ensure tenant scoping
        and filtering remain correct for each request.
        """
        qs = (
            self.model.objects.select_related("feature_type", "feature_type__display_category")
            .filter(feature_type__display_category__isnull=False)
            .annotate(
                int_id=RawSQL("hashtext(CAST(mapping_spatialfeature.id AS TEXT))", []),
                feature_type_name=F("feature_type__name"),
                display_category_name=F("feature_type__display_category__name"),
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
        return qs

    @property
    def queryset(self):  # noqa: D401 - property used by django-vectortiles
        return self._build_base_queryset()

    # If future library versions start calling get_queryset(), keep a compatible method.
    def get_queryset(self):  # pragma: no cover - compatibility shim
        return self.queryset
