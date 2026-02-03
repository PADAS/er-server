"""
Serializers for ObservationSegment models.
"""

from rest_framework import serializers

from observations.models import ObservationSegment
from utils import json as utils_json


class ObservationSegmentSerializer(serializers.ModelSerializer):
    """Serializer for individual ObservationSegment instances."""

    subject_id = serializers.UUIDField(source="subject.id", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = ObservationSegment
        fields = [
            "id",
            "subject_id",
            "subject_name",
            "geometry",
            "speed_kmh",
            "time_gap_ms",
            "distance_meters",
            "start_recorded_at",
            "end_recorded_at",
            "exclusion_flags",
        ]


class SubjectTrackSegmentsSerializer(serializers.Serializer):
    """
    Serializer for subject track composed of pre-computed segments.

    Returns a GeoJSON FeatureCollection of LineString segments.
    """

    def to_representation(self, subject):
        """
        Convert subject's segments to GeoJSON FeatureCollection.

        Args:
            subject: Subject instance

        Returns:
            dict: GeoJSON FeatureCollection with segment features
        """
        request = self.context.get("request")
        since = self.context.get("since")
        until = self.context.get("until")
        show_excluded = bool(self.context.get("show_excluded", False))

        # Get subject's segments
        segments_qs = ObservationSegment.objects.filter(subject=subject).select_related("subject")

        # Apply time filters: include segments that overlap the requested window
        if since and until:
            # Segments overlap [since, until] if they start before 'until' and end after 'since'
            segments_qs = segments_qs.filter(
                start_recorded_at__lt=until,
                end_recorded_at__gt=since,
            )
        elif since:
            # Open-ended window [since, +∞): segments that end after 'since'
            segments_qs = segments_qs.filter(end_recorded_at__gt=since)
        elif until:
            # Open-ended window (-∞, until]: segments that start before 'until'
            segments_qs = segments_qs.filter(start_recorded_at__lt=until)

        # Apply exclusion flag behavior: default exclude any truthy flags unless show_excluded
        if not show_excluded:
            segments_qs = segments_qs.filter(exclusion_flags=0)

        # Order by time
        segments_qs = segments_qs.order_by("start_recorded_at")

        # Build GeoJSON FeatureCollection
        features = []
        for segment in segments_qs:
            feature = {
                "type": "Feature",
                "id": str(segment.id),
                "geometry": {
                    "type": "LineString",
                    "coordinates": list(segment.geometry.coords),
                },
                "properties": {
                    "id": str(segment.id),
                    "subject_id": str(subject.id),
                    "subject_name": subject.name,
                    "subject_type": subject.subject_subtype.subject_type.value,
                    "subject_subtype": subject.subject_subtype.value,
                    "start_recorded_at": segment.start_recorded_at.isoformat(),
                    "end_recorded_at": segment.end_recorded_at.isoformat(),
                    "speed_kmh": round(segment.speed_kmh, 2),
                    "time_gap_ms": round(segment.time_gap_ms, 0),
                    "distance_meters": round(segment.distance_meters, 2),
                    "exclusion_flags": segment.exclusion_flags.mask if hasattr(segment.exclusion_flags, "mask") else 0,
                },
            }

            # Add subject presentation properties
            if hasattr(subject, "color"):
                feature["properties"]["stroke"] = subject.color
                feature["properties"]["stroke-opacity"] = 1.0
                feature["properties"]["stroke-width"] = 2

            if subject.image_url:
                from observations.serializers import add_base_url

                feature["properties"]["image"] = add_base_url(request, subject.image_url)

            features.append(feature)

        # Build FeatureCollection
        feature_collection = utils_json.empty_geojson_featurecollection()
        feature_collection["features"] = features

        return feature_collection


class SubjectTrackSegmentsGroupedSerializer(serializers.Serializer):
    """
    Serializer for subject track with contiguous segments merged into a single LineString per group.

    Groups consecutive segments, breaking at:
    - Gaps where end_observation of one segment != start_observation of next
    - (Optional) changes in exclusion_flags if group_by_flags=True

    Each group is flattened into one LineString whose coordinates are the concatenation
    of each segment's coordinates (avoiding duplicate join points). Single segments
    remain simple LineStrings. The FeatureCollection contains one feature per group.
    """

    def to_representation(self, subject):
        """
        Convert subject's segments to grouped GeoJSON FeatureCollection.

        Args:
            subject: Subject instance

        Returns:
            dict: GeoJSON FeatureCollection with grouped segment features
        """
        request = self.context.get("request")
        since = self.context.get("since")
        until = self.context.get("until")
        show_excluded = bool(self.context.get("show_excluded", False))
        group_by_flags = self.context.get("group_by_flags", False)  # Optional: split on flag changes
        max_speed_kmh = self.context.get("max_speed_kmh", None)
        max_gap_ms = self.context.get("max_gap_ms", None)

        # Get subject's segments
        segments_qs = ObservationSegment.objects.filter(subject=subject).select_related(
            "subject", "start_observation", "end_observation"
        )

        # Apply time filters
        # Include any segment that overlaps the [since, until] interval.
        # Overlap logic: start_recorded_at < until AND end_recorded_at > since
        if since and until:
            segments_qs = segments_qs.filter(
                start_recorded_at__lt=until,
                end_recorded_at__gt=since,
            )
        elif since:
            # Segments that end after the start of the window
            segments_qs = segments_qs.filter(end_recorded_at__gt=since)
        elif until:
            # Segments that start before the end of the window
            segments_qs = segments_qs.filter(start_recorded_at__lt=until)

        # Default: exclude any truthy exclusion flags unless show_excluded
        if not show_excluded:
            segments_qs = segments_qs.filter(exclusion_flags=0)

        # Order by time
        segments = list(segments_qs.order_by("start_recorded_at"))

        if not segments:
            feature_collection = utils_json.empty_geojson_featurecollection()
            return feature_collection

        # Group contiguous segments
        features = []
        current_group = []
        current_group_props = None

        for i, segment in enumerate(segments):
            # Determine if this segment continues the current group
            is_contiguous = False
            if current_group:
                prev_segment = current_group[-1]
                # Check if this segment's start observation matches previous end observation
                is_contiguous = prev_segment.end_observation_id == segment.start_observation_id and (
                    not group_by_flags or prev_segment.exclusion_flags == segment.exclusion_flags
                )

                # Apply runtime segmentation thresholds: break if limits exceeded
                if is_contiguous and max_speed_kmh is not None:
                    try:
                        if float(segment.speed_kmh) > float(max_speed_kmh):
                            is_contiguous = False
                    except Exception:
                        # If value is not parseable, do not break on speed
                        pass

                if is_contiguous and max_gap_ms is not None:
                    try:
                        if int(segment.time_gap_ms) > int(max_gap_ms):
                            is_contiguous = False
                    except Exception:
                        # If value is not parseable, do not break on time gap
                        pass

            if not is_contiguous and current_group:
                # Finish the current group and start a new one
                features.append(self._create_grouped_feature(subject, current_group, current_group_props, request))
                current_group = []
                current_group_props = None

            # Add to current group
            current_group.append(segment)
            if current_group_props is None:
                current_group_props = self._get_group_properties(subject, segment)

        # Add the final group
        if current_group:
            features.append(self._create_grouped_feature(subject, current_group, current_group_props, request))

        # Build FeatureCollection
        feature_collection = utils_json.empty_geojson_featurecollection()
        feature_collection["features"] = features

        return feature_collection

    def _get_group_properties(self, subject, first_segment):
        """Build properties for a segment group."""
        return {
            "subject_id": str(subject.id),
            "subject_name": subject.name,
            "subject_type": subject.subject_subtype.subject_type.value if subject.subject_subtype else None,
            "subject_subtype": subject.subject_subtype.value if subject.subject_subtype else None,
            "exclusion_flags": (
                first_segment.exclusion_flags.mask if hasattr(first_segment.exclusion_flags, "mask") else 0
            ),
        }

    def _create_grouped_feature(self, subject, segments, base_props, request):
        """Create a GeoJSON feature from a group of segments."""
        # Merge coordinates for all segments into one LineString
        if not segments:
            return None

        merged_coords = []
        for idx, seg in enumerate(segments):
            seg_coords = list(seg.geometry.coords)
            if idx == 0:
                merged_coords.extend(seg_coords)
            else:
                # Avoid duplicating the first coordinate if it matches the last merged point
                if merged_coords and seg_coords:
                    if merged_coords[-1] == seg_coords[0]:
                        seg_coords = seg_coords[1:]
                merged_coords.extend(seg_coords)

        # Aggregate properties
        total_distance = sum(seg.distance_meters for seg in segments)
        total_duration = sum(seg.time_gap_ms for seg in segments)
        # Guard against extremely small durations that can cause numerical instability
        # Use a minimum threshold of 1 ms before computing average speed
        if total_duration and total_duration >= 1.0:
            avg_speed = total_distance / (total_duration / 1000.0 / 3600.0)
        else:
            avg_speed = 0  # km/h

        first = segments[0]
        last = segments[-1]
        geometry = {
            "type": "LineString",
            "coordinates": merged_coords,
        }
        properties = {
            **base_props,
            "id": str(first.id),  # Use first segment ID as group ID
            "segment_count": len(segments),
            "start_recorded_at": first.start_recorded_at.isoformat(),
            "end_recorded_at": last.end_recorded_at.isoformat(),
            "total_distance_meters": round(total_distance, 2),
            "avg_speed_kmh": round(avg_speed, 2),
            "total_duration_ms": round(total_duration, 0),
            "segment_ids": [str(seg.id) for seg in segments],
        }

        # Add subject presentation properties
        if hasattr(subject, "additional") and subject.additional:
            stroke = subject.additional.get("rgb", "#4264fb")
            properties["stroke"] = stroke
            properties["stroke-opacity"] = 1.0
            properties["stroke-width"] = 2

        if subject.image_url:
            from observations.serializers import add_base_url

            properties["image"] = add_base_url(request, subject.image_url)

        return {
            "type": "Feature",
            "id": properties["id"],
            "geometry": geometry,
            "properties": properties,
        }
