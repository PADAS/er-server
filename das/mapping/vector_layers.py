import logging

from vectortiles import VectorLayer

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import Transform
from django.db.models import Case, CharField, F, FloatField, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Concat

from mapping.filters import SpatialFeatureFilterSet
from mapping.models import SpatialFeature
from utils.tenant import get_tenant_settings

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
            "external_id",
            "description",
            "feature_type_id",
            "feature_type_name",
            "display_category_name",
            "attributes",
            *self.presentation_keys,
        )

    def get_queryset(self):  # pragma: no cover - compatibility shim
        return self._build_base_queryset()

    def _build_base_queryset(self):
        # First pass: extract the raw image value (could be relative like /static/foo.svg)
        qs = (
            self.model.objects.select_related("feature_type", "feature_type__display_category")
            .filter(feature_type__display_category__isnull=False)
            .annotate(
                feature_type_name=F("feature_type__name"),
                display_category_name=F("feature_type__display_category__name"),
                geom=Transform(Cast(F("feature_geometry"), gis_models.GeometryField()), 3857),
                **self._extract_presentation_json_keys(),
                raw_image=Case(
                    When(
                        presentation__image__has_key="image",
                        then=KeyTextTransform("image", KeyTextTransform("image", F("presentation"))),
                    ),
                    When(
                        presentation__has_key="image",
                        then=KeyTextTransform("image", F("presentation")),
                    ),
                    When(
                        presentation__has_key="icon_url",
                        then=KeyTextTransform("icon_url", F("presentation")),
                    ),
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
                ),
            )
        )
        tenant = get_tenant_settings()
        base_root = getattr(tenant, "url", None)
        if not base_root:
            raise RuntimeError("Tenant context required to build absolute image URLs for spatial feature tiles.")
        base_root = base_root.rstrip("/")

        # Second pass: normalize relative raw_image values to absolute, leave existing absolute/data URIs untouched.
        # Can't do startswith tests on the alias inside the same annotate call; requires two-pass.
        qs = qs.annotate(
            image=Case(
                # Already absolute or data URI
                When(raw_image__startswith="http://", then=F("raw_image")),
                When(raw_image__startswith="https://", then=F("raw_image")),
                When(raw_image__startswith="data:", then=F("raw_image")),
                # Null -> keep null
                When(raw_image__isnull=True, then=Value(None)),
                # Relative path starting with /
                When(
                    raw_image__startswith="/",
                    then=Concat(Value(base_root), F("raw_image")),
                ),
                # Relative path without leading /
                When(
                    raw_image__isnull=False,
                    then=Concat(Value(base_root + "/"), F("raw_image")),
                ),
                default=Value(None),
                output_field=CharField(),
            )
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

            # Return a Case expression directly (tests assert isinstance(..., Case))
            annotations[key] = Case(
                When(presentation__has_key=key, then=then_self),
                When(feature_type__presentation__has_key=key, then=then_ft),
                default=Value(None),
                output_field=output_field,
            )

        return annotations
