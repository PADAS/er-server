import logging

from vectortiles import VectorLayer

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import Transform
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import Case, CharField, F, TextField, Value, When
from django.db.models.expressions import RawSQL
from django.db.models.functions import Cast

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature

logger = logging.getLogger(__name__)


class SpatialFeatureLayer(VectorLayer):
    model = SpatialFeature
    id = "spatial_features"
    # send the uuid 'id' so clients can still correlate
    # int_id is included to be compatible with mapboxgl's feature state interfaces
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
        "presentation_json",
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
                presentation_json=Cast(F("feature_type__presentation"), output_field=TextField()),
                image=Case(
                    # Nested object pattern: {"image": {"image": "/path.svg", ...}}
                    When(
                        presentation__image__has_key="image",
                        then=KeyTextTransform("image", KeyTextTransform("image", F("presentation"))),
                    ),
                    # Direct string
                    When(
                        presentation__has_key="image",
                        then=KeyTextTransform("image", F("presentation")),
                    ),
                    # Direct icon_url
                    When(
                        presentation__has_key="icon_url",
                        then=KeyTextTransform("icon_url", F("presentation")),
                    ),
                    # FeatureType nested object
                    When(
                        feature_type__presentation__image__has_key="image",
                        then=KeyTextTransform("image", KeyTextTransform("image", F("feature_type__presentation"))),
                    ),
                    # FeatureType direct string
                    When(
                        feature_type__presentation__has_key="image",
                        then=KeyTextTransform("image", F("feature_type__presentation")),
                    ),
                    # FeatureType icon_url
                    When(
                        feature_type__presentation__has_key="icon_url",
                        then=KeyTextTransform("icon_url", F("feature_type__presentation")),
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
