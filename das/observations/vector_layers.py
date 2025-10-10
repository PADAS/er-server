import logging

from vectortiles import VectorLayer

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import Transform
from django.db.models import (
    Case,
    CharField,
    F,
    FloatField,
    IntegerField,
    Value,
    When,
    Window,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Lag, Lead

from analyzers.models import ObservationAnnotator
from observations.filters import ObservationVectorTileFilterSet
from observations.models import Observation

logger = logging.getLogger(__name__)


class ObservationVectorLayer(VectorLayer):
    """
    Vector layer for observations with track segmentation capabilities.

    Supports sharding by:
    - Time gaps (max hours between observations)
    - Speed thresholds (impossible travel speeds)
    """

    model = Observation
    id = "observations"
    min_zoom = 3
    max_zoom = 24
    filterset_class = ObservationVectorTileFilterSet

    # Default thresholds for segmentation
    DEFAULT_MAX_TIME_GAP_HOURS = 24
    DEFAULT_SPEED_THRESHOLD_KMH = 200.0

    @property
    def presentation_keys(self):
        """Keys for styling the observations in the vector tile."""
        return ["stroke", "stroke-width", "stroke-opacity"]

    @property
    def tile_fields(self):
        """Fields to include in the vector tile."""
        return (
            "id",
            "recorded_at",
            "subject_id",
            "subject_name",
            "source_id",
            "source_name",
            "track_segment_id",
            "segment_order",
            "speed_kmh",
            "additional",
            *self.presentation_keys,
        )

    def get_queryset(self):
        """Build the base queryset with track segmentation logic."""
        return self._build_base_queryset()

    def _build_base_queryset(self):
        """Build the queryset with track segmentation annotations."""
        # Get filter parameters
        max_time_gap_hours = self._get_max_time_gap_hours()
        speed_threshold_kmh = self._get_speed_threshold_kmh()

        # Base queryset with necessary joins and annotations
        qs = self.model.objects.select_related("source", "source__provider").annotate(
            # Transform geometry to Web Mercator for vector tiles
            geom=Transform(Cast(F("location"), gis_models.GeometryField()), 3857),
            # Subject information
            subject_id=F("source__subjectsource__subject_id"),
            subject_name=F("source__subjectsource__subject__name"),
            # Source information
            source_name=F("source__manufacturer_id"),
            # Calculate distances and time gaps for speed calculation
            distance_preceding=Case(
                When(
                    recorded_at__isnull=False,
                    then=Window(
                        expression=Lag("location"),
                        order_by=F("recorded_at"),
                    ),
                ),
                default=Value(None),
                output_field=gis_models.GeometryField(),
            ),
            time_lapse_preceding=Case(
                When(
                    recorded_at__isnull=False,
                    then=Window(
                        expression=Lag("recorded_at"),
                        order_by=F("recorded_at"),
                    ),
                ),
                default=Value(None),
                output_field=CharField(),
            ),
            distance_following=Case(
                When(
                    recorded_at__isnull=False,
                    then=Window(
                        expression=Lead("location"),
                        order_by=F("recorded_at"),
                    ),
                ),
                default=Value(None),
                output_field=gis_models.GeometryField(),
            ),
            time_lapse_following=Case(
                When(
                    recorded_at__isnull=False,
                    then=Window(
                        expression=Lead("recorded_at"),
                        order_by=F("recorded_at"),
                    ),
                ),
                default=Value(None),
                output_field=CharField(),
            ),
        )

        # Add track segmentation logic
        qs = self._add_track_segmentation(qs, max_time_gap_hours, speed_threshold_kmh)

        # Add presentation styling
        qs = self._add_presentation_styling(qs)

        return qs

    def _get_max_time_gap_hours(self) -> float:
        """Get max time gap from request parameters."""
        if hasattr(self, "request") and self.request:
            try:
                return float(self.request.query_params.get("max_time_gap_hours", self.DEFAULT_MAX_TIME_GAP_HOURS))
            except (ValueError, TypeError):
                pass
        return self.DEFAULT_MAX_TIME_GAP_HOURS

    def _get_speed_threshold_kmh(self) -> float:
        """Get speed threshold from request parameters."""
        if hasattr(self, "request") and self.request:
            try:
                return float(self.request.query_params.get("speed_threshold_kmh", self.DEFAULT_SPEED_THRESHOLD_KMH))
            except (ValueError, TypeError):
                pass
        return self.DEFAULT_SPEED_THRESHOLD_KMH

    def _add_track_segmentation(self, qs, max_time_gap_hours: float, speed_threshold_kmh: float):
        """Add track segmentation logic using ObservationAnnotator's reusable methods."""

        # Use ObservationAnnotator's new segmentation method that includes distance/speed calculations
        annotator = ObservationAnnotator()

        # Apply the complete segmentation logic in one call
        return annotator.annotate_with_segmentation(
            qs, max_time_gap_hours=max_time_gap_hours, speed_threshold_kmh=speed_threshold_kmh
        ).order_by("source__subjectsource__subject_id", "recorded_at")

    def _add_presentation_styling(self, qs):
        """Add presentation styling annotations."""
        # Extract presentation keys from subject's additional field
        presentation_annotations = self._extract_presentation_json_keys()

        # Add image handling similar to spatial features
        image_annotation = Case(
            When(
                source__subjectsource__subject__additional__has_key="image",
                then=KeyTextTransform("image", F("source__subjectsource__subject__additional")),
            ),
            When(
                source__subjectsource__subject__additional__has_key="icon_url",
                then=KeyTextTransform("icon_url", F("source__subjectsource__subject__additional")),
            ),
            default=Value(None),
            output_field=CharField(),
        )

        # Add RGB color conversion for stroke color
        stroke_color_annotation = Case(
            When(
                source__subjectsource__subject__additional__has_key="rgb",
                then=KeyTextTransform("rgb", F("source__subjectsource__subject__additional")),
            ),
            default=Value("#3388ff"),  # Default blue color
            output_field=CharField(),
        )

        # Override stroke color if not already set in presentation_annotations
        if "stroke" not in presentation_annotations:
            presentation_annotations["stroke"] = stroke_color_annotation

        # Add default values for missing presentation keys
        default_annotations = {
            "stroke-width": Case(
                When(
                    source__subjectsource__subject__additional__has_key="stroke-width",
                    then=Cast(
                        KeyTextTransform("stroke-width", F("source__subjectsource__subject__additional")),
                        IntegerField(),
                    ),
                ),
                default=Value(2),
                output_field=IntegerField(),
            ),
            "stroke-opacity": Case(
                When(
                    source__subjectsource__subject__additional__has_key="stroke-opacity",
                    then=Cast(
                        KeyTextTransform("stroke-opacity", F("source__subjectsource__subject__additional")),
                        FloatField(),
                    ),
                ),
                default=Value(0.8),
                output_field=FloatField(),
            ),
        }

        # Merge all annotations, with presentation_annotations taking precedence
        all_annotations = {**default_annotations, **presentation_annotations, "image": image_annotation}

        return qs.annotate(**all_annotations)

    def _extract_presentation_json_keys(self):
        """Extract presentation keys from subject's additional JSON field."""
        annotations = {}

        for key in self.presentation_keys:
            # Skip image as it's handled separately
            if key == "image":
                continue

            # Determine output field type
            if key in {"stroke-width"}:
                output_field = IntegerField()
                then_value = Cast(
                    KeyTextTransform(key, F("source__subjectsource__subject__additional")), IntegerField()
                )
            elif key in {"stroke-opacity"}:
                output_field = FloatField()
                then_value = Cast(KeyTextTransform(key, F("source__subjectsource__subject__additional")), FloatField())
            else:
                output_field = CharField()
                then_value = KeyTextTransform(key, F("source__subjectsource__subject__additional"))

            # Create Case expression for each presentation key
            annotations[key] = Case(
                When(source__subjectsource__subject__additional__has_key=key, then=then_value),
                default=Value(None),
                output_field=output_field,
            )

        return annotations

    def get_tile_data(self, tile, layer_name=None):
        """
        Return tile data using the superclass implementation.
        Track segmentation is now handled at the database level.
        """
        return super().get_tile_data(tile, layer_name)
