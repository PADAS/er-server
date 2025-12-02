"""
Vector layers for ObservationSegments.

Provides Mapbox Vector Tile layers for rendering pre-computed track segments.
"""

from vectortiles import VectorLayer

from django.db.models import CharField, F, Value
from django.db.models.functions import Coalesce

from observations.filters import ObservationSegmentVectorTileFilterSet
from observations.models import ObservationSegment


class ObservationSegmentVectorLayer(VectorLayer):
    """
    Vector layer for pre-computed observation segments.

    Returns LineString features representing segments between consecutive observations.
    Each segment includes computed metrics (speed, time gap, distance) and
    presentation properties for client-side rendering.
    """

    model = ObservationSegment
    id = "observation_segments"
    geom_field = "geometry"
    min_zoom = 3
    max_zoom = 24
    filterset_class = ObservationSegmentVectorTileFilterSet

    # ------------------------------------------------------------------ #
    # Presentation / appearance
    # ------------------------------------------------------------------ #
    @property
    def presentation_keys(self):
        return ["stroke", "stroke-width", "stroke-opacity"]

    @property
    def tile_fields(self):
        return (
            "id",
            "subject_id",
            "subject_name",
            "start_recorded_at",
            "end_recorded_at",
            "speed_kmh",
            "time_gap_ms",
            "distance_meters",
            "exclusion_flags",
        )

    # ------------------------------------------------------------------ #
    # Query construction
    # ------------------------------------------------------------------ #
    def get_queryset(self):
        """
        Build queryset for segments with annotations.

        By default, excludes segments with non-zero exclusion flags.
        """
        qs = self.model.objects.select_related("subject", "subject__subject_subtype")

        # Apply default exclusion unless 'show_excluded=true'
        if hasattr(self, "request") and self.request:
            show_excluded = (self.request.GET.get("show_excluded", "false") or "false").lower() == "true"
            if not show_excluded:
                qs = qs.filter(exclusion_flags=0)

        return qs.order_by("start_recorded_at")

    def _get_vector_tile_annotations(self):
        """
        Return annotations for vector tile output.
        """
        return {
            "subject_name": Coalesce(F("subject__name"), Value("", output_field=CharField())),
        }

    def get_vector_tile_queryset(self, z=None, x=None, y=None):
        """
        Build queryset for vector tile extraction with tile-specific optimizations.
        """
        qs = self.get_queryset()
        annotations = self._get_vector_tile_annotations()
        return qs.annotate(**annotations)

    # ------------------------------------------------------------------ #
    # Styling / presentation
    # ------------------------------------------------------------------ #
    def get_presentation_properties(self, obj):
        """
        Return presentation properties for a segment feature.
        Uses subject's color/style settings.
        """
        subject = obj.subject
        additional = getattr(subject, "additional", {}) or {}

        # Default track styling
        stroke = additional.get("rgb", "#4264fb")  # Default blue
        stroke_width = 2.0
        stroke_opacity = 0.8

        # You can add logic here to vary stroke based on speed, time_gap, etc.
        # For example: thicker lines for faster speeds, dashed for long time gaps

        return {
            "stroke": stroke,
            "stroke-width": stroke_width,
            "stroke-opacity": stroke_opacity,
        }

    def as_vector_tile_feature(self, obj):
        """
        Return feature dict for vector tile rendering.
        """
        props = {
            "id": str(obj.id),
            "subject_id": str(obj.subject_id),
            "subject_name": getattr(obj, "subject_name", ""),
            "start_recorded_at": obj.start_recorded_at.isoformat() if obj.start_recorded_at else None,
            "end_recorded_at": obj.end_recorded_at.isoformat() if obj.end_recorded_at else None,
            "speed_kmh": round(obj.speed_kmh, 2) if obj.speed_kmh else None,
            "time_gap_ms": round(obj.time_gap_ms, 0) if obj.time_gap_ms else None,
            "distance_meters": round(obj.distance_meters, 2) if obj.distance_meters else None,
            "exclusion_flags": obj.exclusion_flags.mask if hasattr(obj.exclusion_flags, "mask") else 0,
        }

        # Add presentation properties
        props.update(self.get_presentation_properties(obj))

        return {
            "id": str(obj.id),
            "geometry": obj.geometry,
            "properties": props,
        }

    def get_tile_data(self, tile, layer_name=None):
        """Use superclass tile builder."""
        return super().get_tile_data(tile, layer_name)
