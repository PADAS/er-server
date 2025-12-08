"""
Vector layers for ObservationSegments.

Provides Mapbox Vector Tile layers for rendering pre-computed track segments.
"""

from vectortiles import VectorLayer

from django.db.models import BooleanField, Case, CharField, F, Value, When, Window
from django.db.models.functions import Coalesce, RowNumber

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
            "is_latest",
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

        # Flag the latest segment per subject within the filtered queryset
        rn = Window(
            expression=RowNumber(),
            partition_by=F("subject_id"),
            order_by=[F("end_recorded_at").desc()],
        )
        qs = qs.annotate(_rn=rn)
        qs = qs.annotate(
            is_latest=Case(When(_rn=1, then=Value(True)), default=Value(False), output_field=BooleanField())
        )

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

        # Ensure ISO 8601 with 'T' separator for lexicographic sorting
        def _iso(dt):
            return dt.isoformat(sep="T", timespec="milliseconds") if dt else None

        props = {
            "id": str(obj.id),
            "subject_id": str(obj.subject_id),
            "subject_name": getattr(obj, "subject_name", ""),
            "start_recorded_at": _iso(obj.start_recorded_at),
            "end_recorded_at": _iso(obj.end_recorded_at),
            "speed_kmh": round(obj.speed_kmh, 2) if obj.speed_kmh else None,
            "time_gap_ms": round(obj.time_gap_ms, 0) if obj.time_gap_ms else None,
            "distance_meters": round(obj.distance_meters, 2) if obj.distance_meters else None,
            "exclusion_flags": obj.exclusion_flags.mask if hasattr(obj.exclusion_flags, "mask") else 0,
            "is_latest": bool(getattr(obj, "is_latest", False)),
        }

        # Add presentation properties
        props.update(self.get_presentation_properties(obj))

        return {
            "id": str(obj.id),
            "geometry": obj.geometry,
            "properties": props,
        }

    def get_tile_data(self, tile, layer_name=None):
        """Build tile data and append endpoint point features for arrows (z>=10)."""
        base_features = super().get_tile_data(tile, layer_name)

        # Safely append point features for each LineString segment
        # Zoom-gate to avoid payload bloat at low zooms
        z = getattr(tile, "z", None)
        segment_points = []
        if z is None or z < 10:
            # Below threshold, return only base line features
            return base_features

        for feat in base_features:
            geom = feat.get("geometry")
            props = feat.get("properties", {})
            # Only process LineStrings
            if getattr(geom, "geom_type", None) == "LineString":
                try:
                    coords = list(getattr(geom, "coords", []))
                except Exception:
                    coords = []

                if len(coords) >= 2:
                    start = coords[0]
                    end = coords[-1]

                    # Compute bearing from start -> end
                    bearing = self._compute_bearing_deg(start[1], start[0], end[1], end[0])

                    # Start point feature (arrow towards next)
                    segment_points.append(
                        {
                            "id": props.get("id", "") + ":start",
                            "geometry": self._make_point(start),
                            "properties": {
                                **props,
                                "kind": "segment_start",
                                "bearing_to_next": bearing,
                            },
                        }
                    )

                    # End point feature (arrow from previous)
                    segment_points.append(
                        {
                            "id": props.get("id", "") + ":end",
                            "geometry": self._make_point(end),
                            "properties": {
                                **props,
                                "kind": "segment_end",
                                "bearing_from_prev": bearing,
                            },
                        }
                    )

        return base_features + segment_points

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _compute_bearing_deg(lat1, lon1, lat2, lon2):
        """Compute initial bearing from (lat1, lon1) to (lat2, lon2) in degrees [0,360)."""
        import math

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_lambda = math.radians(lon2 - lon1)

        x = math.sin(d_lambda) * math.cos(phi2)
        y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
        theta = math.atan2(x, y)
        bearing = (math.degrees(theta) + 360.0) % 360.0
        return round(bearing, 2)

    @staticmethod
    def _make_point(coord):
        """Create a GEOS Point from (lon, lat[, alt])."""
        try:
            from django.contrib.gis.geos import Point
        except Exception:
            # Fallback: return original tuple; renderer may handle plain coords
            return coord

        if len(coord) >= 3:
            return Point(coord[0], coord[1], coord[2])
        return Point(coord[0], coord[1])
