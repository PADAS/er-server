import logging

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
from vectortiles import VectorLayer

from observations.filters import ObservationVectorTileFilterSet
from observations.models import Observation

from datetime import datetime


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
        return [
            "stroke",
            "stroke-width",
            "stroke-opacity"
        ]

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
        qs = (
            self.model.objects
            .select_related("source", "source__provider")
            .annotate(
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
                        )
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
                        )
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
                        )
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
                        )
                    ),
                    default=Value(None),
                    output_field=CharField(),
                ),
            )
        )

        # Add track segmentation logic
        qs = self._add_track_segmentation(qs, max_time_gap_hours, speed_threshold_kmh)

        # Add presentation styling
        qs = self._add_presentation_styling(qs)

        return qs

    def _get_max_time_gap_hours(self) -> float:
        """Get max time gap from request parameters."""
        if hasattr(self, 'request') and self.request:
            try:
                return float(self.request.query_params.get('max_time_gap_hours', self.DEFAULT_MAX_TIME_GAP_HOURS))
            except (ValueError, TypeError):
                pass
        return self.DEFAULT_MAX_TIME_GAP_HOURS

    def _get_speed_threshold_kmh(self) -> float:
        """Get speed threshold from request parameters."""
        if hasattr(self, 'request') and self.request:
            try:
                return float(self.request.query_params.get('speed_threshold_kmh', self.DEFAULT_SPEED_THRESHOLD_KMH))
            except (ValueError, TypeError):
                pass
        return self.DEFAULT_SPEED_THRESHOLD_KMH

    def _add_track_segmentation(self, qs, max_time_gap_hours: float, speed_threshold_kmh: float):
        """Add track segmentation logic to the queryset."""
        # This is a simplified version - in practice, you'd want to use raw SQL
        # for complex window functions with distance calculations

        # For now, we'll add basic annotations and handle segmentation in post-processing
        # In a production system, you'd want to use raw SQL similar to the pattern in
        # das/analyzers/models/annotations.py

        return qs.annotate(
            # Basic speed calculation (simplified)
            speed_kmh=Value(0.0, output_field=FloatField()),
            track_segment_id=Value(1, output_field=IntegerField()),
            segment_order=Value(1, output_field=IntegerField()),
        )

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
                    then=Cast(KeyTextTransform("stroke-width", F("source__subjectsource__subject__additional")), IntegerField())
                ),
                default=Value(2),
                output_field=IntegerField(),
            ),
            "stroke-opacity": Case(
                When(
                    source__subjectsource__subject__additional__has_key="stroke-opacity",
                    then=Cast(KeyTextTransform("stroke-opacity", F("source__subjectsource__subject__additional")), FloatField())
                ),
                default=Value(0.8),
                output_field=FloatField(),
            )
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
                then_value = Cast(KeyTextTransform(key, F("source__subjectsource__subject__additional")), IntegerField())
            elif key in {"stroke-opacity"}:
                output_field = FloatField()
                then_value = Cast(KeyTextTransform(key, F("source__subjectsource__subject__additional")), FloatField())
            else:
                output_field = CharField()
                then_value = KeyTextTransform(key, F("source__subjectsource__subject__additional"))

            # Create Case expression for each presentation key
            annotations[key] = Case(
                When(
                    source__subjectsource__subject__additional__has_key=key,
                    then=then_value
                ),
                default=Value(None),
                output_field=output_field,
            )

        return annotations

    def _convert_rgb_to_hex(self, rgb_string):
        """Convert RGB string (e.g., '100,150,200') to hex color format."""
        if not rgb_string:
            return None
        try:
            # Parse RGB string like "100,150,200"
            parts = rgb_string.split(",")
            if len(parts) == 3:
                r, g, b = [int(x.strip()) for x in parts]
                # Ensure values are in valid range
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, AttributeError):
            pass
        return None

    def get_tile_data(self, tile, layer_name=None):
        """
        Override to implement custom track segmentation logic.

        This method processes the queryset results to create track segments
        based on time gaps and speed thresholds.
        """
        # Get the base data
        features = super().get_tile_data(tile, layer_name)

        # Apply track segmentation logic here
        # This would group observations into track segments based on:
        # 1. Time gaps between consecutive observations
        # 2. Speed thresholds for impossible travel

        return self._segment_tracks(features)

    def _segment_tracks(self, features):
        """
        Segment observations into tracks based on time gaps and speed thresholds.

        This is a simplified implementation - in practice, you'd want to do this
        at the database level using raw SQL for better performance.
        """
        if not features:
            return features

        # Group by subject
        subject_groups = {}
        for feature in features:
            subject_id = feature.get('properties', {}).get('subject_id')
            if subject_id not in subject_groups:
                subject_groups[subject_id] = []
            subject_groups[subject_id].append(feature)

        segmented_features = []
        segment_id_counter = 1

        for subject_id, subject_features in subject_groups.items():
            # Sort by recorded_at
            subject_features.sort(key=lambda x: x.get('properties', {}).get('recorded_at', ''))

            # Apply segmentation logic
            segments = self._create_track_segments(
                subject_features,
                segment_id_counter
            )
            segmented_features.extend(segments)
            segment_id_counter += len(segments)

        return segmented_features

    def _create_track_segments(self, features, start_segment_id):
        """
        Create track segments from a list of features for a single subject.
        """
        if not features:
            return []

        segments = []
        current_segment = []
        segment_id = start_segment_id

        max_time_gap_hours = self._get_max_time_gap_hours()
        speed_threshold_kmh = self._get_speed_threshold_kmh()

        for i, feature in enumerate(features):
            if not current_segment:
                # Start new segment
                current_segment.append(feature)
            else:
                # Check if we should break the segment
                should_break = self._should_break_segment(
                    current_segment[-1],
                    feature,
                    max_time_gap_hours,
                    speed_threshold_kmh
                )

                if should_break:
                    # Finalize current segment and start new one
                    segments.extend(self._finalize_segment(current_segment, segment_id))
                    segment_id += 1
                    current_segment = [feature]
                else:
                    current_segment.append(feature)

        # Add the last segment
        if current_segment:
            segments.extend(self._finalize_segment(current_segment, segment_id))

        return segments

    def _should_break_segment(self, prev_feature, current_feature, max_time_gap_hours, speed_threshold_kmh):
        """Determine if we should break the track segment."""
        prev_props = prev_feature.get('properties', {})
        current_props = current_feature.get('properties', {})

        # Check time gap
        try:
            prev_time = datetime.fromisoformat(prev_props.get('recorded_at', '').replace('Z', '+00:00'))
            current_time = datetime.fromisoformat(current_props.get('recorded_at', '').replace('Z', '+00:00'))

            time_diff = current_time - prev_time
            if time_diff.total_seconds() > max_time_gap_hours * 3600:
                return True
        except (ValueError, TypeError):
            pass

        # Check speed threshold (simplified - would need proper distance calculation)
        # This is a placeholder - real implementation would calculate actual speed
        speed = current_props.get('speed_kmh', 0)
        if speed > speed_threshold_kmh:
            return True

        return False

    def _finalize_segment(self, segment_features, segment_id):
        """Finalize a track segment by adding segment metadata."""
        for i, feature in enumerate(segment_features):
            if 'properties' not in feature:
                feature['properties'] = {}

            feature['properties']['track_segment_id'] = segment_id
            feature['properties']['segment_order'] = i + 1

        return segment_features
