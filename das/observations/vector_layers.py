from vectortiles import VectorLayer

from django.db.models import Case, CharField, F, FloatField, Value, When
from django.db.models.functions import Cast, Coalesce

from observations.filters import ObservationVectorTileFilterSet
from observations.models import Observation


class ObservationVectorLayer(VectorLayer):
    """
    Vector layer for observations with track segmentation capabilities.
    Handles:
      • Time gaps between observations
      • Speed thresholds for impossible travel speeds
    """

    model = Observation
    id = "observations"
    geom_field = "location"
    min_zoom = 3
    max_zoom = 24
    filterset_class = ObservationVectorTileFilterSet

    DEFAULT_MAX_TIME_GAP_HOURS = 24
    DEFAULT_SPEED_THRESHOLD_KMH = 200.0

    # ------------------------------------------------------------------ #
    # Presentation / appearance
    # ------------------------------------------------------------------ #
    @property
    def presentation_keys(self):
        """Keys for styling the observations in the vector tile."""
        return ["stroke", "stroke-width", "stroke-opacity"]

    @property
    def tile_fields(self):
        """Fields included in the vector tile output."""
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

    # ------------------------------------------------------------------ #
    # Query construction
    # ------------------------------------------------------------------ #
    def get_queryset(self):
        """Builds base queryset for ORM use (not tiles)."""
        qs = (
            self.model.objects.select_related("source", "source__provider")
            .filter(location__isnull=False)
            .order_by("recorded_at")
        )
        qs = self._add_track_segmentation(qs, self._get_max_time_gap_hours(), self._get_speed_threshold_kmh())
        qs = self._add_presentation_styling(qs)
        return qs

    def get_vector_tile_queryset(self, z=None, x=None, y=None):
        """
        Build queryset for vector tile extraction.
        This is the method vectortiles.views.MVTView calls internally.
        """
        qs = self.get_queryset()

        # ✅ Ensure annotation happens before values() is called downstream
        annotations = {
            "subject_id": Coalesce(F("source__subjectsource__subject_id"), Value(None)),
            "subject_name": Coalesce(F("source__subjectsource__subject__name"), Value("", output_field=CharField())),
            "source_name": Coalesce(
                F("source__model_name"),
                F("source__manufacturer_id"),
                Value("", output_field=CharField()),
            ),
        }
        return qs.annotate(**annotations)

    # ------------------------------------------------------------------ #
    # Parameter helpers
    # ------------------------------------------------------------------ #
    def _get_max_time_gap_hours(self) -> float:
        try:
            return float(self.request.query_params.get("max_time_gap_hours"))
        except Exception:
            return self.DEFAULT_MAX_TIME_GAP_HOURS

    def _get_speed_threshold_kmh(self) -> float:
        try:
            return float(self.request.query_params.get("speed_threshold_kmh"))
        except Exception:
            return self.DEFAULT_SPEED_THRESHOLD_KMH

    # ------------------------------------------------------------------ #
    # Segmentation
    # ------------------------------------------------------------------ #
    def _add_track_segmentation(self, qs, max_time_gap_hours, speed_threshold_kmh):
        """Stub segmentation for ORM completeness."""
        return qs.annotate(
            track_segment_id=Value(0),
            segment_order=Value(1),
            speed_kmh=Value(0.0, output_field=FloatField()),
        )

    # ------------------------------------------------------------------ #
    # Styling / presentation
    # ------------------------------------------------------------------ #
    def _add_presentation_styling(self, qs):
        """Adds color/width/opacity styling based on subject additional data."""
        stroke = Case(
            When(
                source__subjectsource__subject__additional__has_key="stroke",
                then=F("source__subjectsource__subject__additional__stroke"),
            ),
            default=Value(None),
            output_field=CharField(),
        )
        stroke_width = Case(
            When(
                source__subjectsource__subject__additional__has_key="stroke-width",
                then=Cast(
                    F("source__subjectsource__subject__additional__stroke-width"),
                    FloatField(),
                ),
            ),
            default=Value(2.0),
            output_field=FloatField(),
        )
        stroke_opacity = Case(
            When(
                source__subjectsource__subject__additional__has_key="stroke-opacity",
                then=Cast(
                    F("source__subjectsource__subject__additional__stroke-opacity"),
                    FloatField(),
                ),
            ),
            default=Value(0.8),
            output_field=FloatField(),
        )
        return qs.annotate(stroke=stroke, **{"stroke-width": stroke_width, "stroke-opacity": stroke_opacity})

    # ------------------------------------------------------------------ #
    def get_tile_data(self, tile, layer_name=None):
        """Use superclass tile builder."""
        return super().get_tile_data(tile, layer_name)
