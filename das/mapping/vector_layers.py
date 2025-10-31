import logging

from vectortiles import VectorLayer

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Case, CharField, F, FloatField, Value, When
from django.db.models.expressions import RawSQL
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature

logger = logging.getLogger(__name__)


class SpatialFeatureLayer(VectorLayer):
    model = SpatialFeature
    id = "spatial_features"
    min_zoom = 3
    max_zoom = 24
    filterset_class = SpatialFeatureFilterSet

    @property
    def presentation_keys(self):
        return [
            "stroke",
            "stroke-width",
            "stroke-opacity",
            "fill",
            "fill-color",
            "fill-opacity",
            "width",
            "height",
            "image",
        ]

    @property
    def tile_fields(self):
        return (
            "id",
            "name",
            "short_name",
            "description",
            "attributes",
            *self.presentation_keys,
        )

    def _build_base_queryset(self, zoom=None):
        """
        Build the base queryset for vector tiles.
        """
        image_expr = Case(
            When(
                presentation__image__has_key="image",
                then=KeyTextTransform("image", KeyTextTransform("image", F("presentation"))),
            ),
            When(presentation__has_key="image", then=KeyTextTransform("image", F("presentation"))),
            When(presentation__has_key="icon_url", then=KeyTextTransform("icon_url", F("presentation"))),
            When(
                feature_type__presentation__image__has_key="image",
                then=KeyTextTransform("image", KeyTextTransform("image", F("feature_type__presentation"))),
            ),
            When(
                feature_type__presentation__has_key="image",
                then=KeyTextTransform("image", F("feature_type__presentation")),
            ),
            When(
                feature_type__presentation__has_key="icon_url",
                then=KeyTextTransform("icon_url", F("feature_type__presentation")),
            ),
            default=Value(None),
            output_field=CharField(),
        )

        tolerance = self._zoom_tolerance(zoom)

        return (
            self.model.objects.select_related("feature_type", "feature_type__display_category")
            .filter(feature_type__is_visible=True)
            .filter(feature_type__display_category__isnull=False)
            .annotate(
                feature_type_name=F("feature_type__name"),
                display_category_name=F("feature_type__display_category__name"),
                # Simplify at DB level in native SRID 4326
                geom=RawSQL(
                    """
                    ST_SimplifyPreserveTopology(feature_geometry::geometry, %s)
                    """,
                    (tolerance,),
                    output_field=gis_models.GeometryField(srid=4326),
                ),
                **self._extract_presentation_json_keys(),
                image=image_expr,
            )
        )

    def get_queryset(self):  # pragma: no cover - compatibility shim
        """
        Return queryset with geometries transformed to 3857 in Python.
        This avoids PostGIS / PROJ transform limitations entirely.

        """
        qs = self._build_base_queryset()
        for obj in qs:
            geom = getattr(obj, "geom", None)
            if geom and isinstance(geom, GEOSGeometry):
                try:
                    geom.transform(3857)  # local reprojection (GEOS)
                    obj.geom = geom
                except Exception:
                    logger.exception(
                        "Failed to transform geometry for SpatialFeature id=%s",
                        getattr(obj, "id", None),
                    )
        return qs

    def _extract_presentation_json_keys(self):
        annotations = {}

        for key in self.presentation_keys:
            # Prevent duplicate with explicit image annotation
            if key == "image":
                continue

            if key in {"stroke-width", "width", "height", "stroke-opacity", "fill-opacity"}:
                output_field = FloatField()
                then_self = Cast(KeyTextTransform(key, F("presentation")), FloatField())
                then_ft = Cast(KeyTextTransform(key, F("feature_type__presentation")), FloatField())
            else:
                output_field = CharField()
                then_self = KeyTextTransform(key, F("presentation"))
                then_ft = KeyTextTransform(key, F("feature_type__presentation"))

            annotations[key] = Case(
                When(presentation__has_key=key, then=then_self),
                When(feature_type__presentation__has_key=key, then=then_ft),
                default=Value(None),
                output_field=output_field,
            )

        return annotations

    def _zoom_tolerance(self, zoom):  # Returns a simplification tolerance in degrees (EPSG:4326).
        if zoom is None:
            return 0
        return max(0.00001, 0.1 * (2 ** (3 - zoom)))
