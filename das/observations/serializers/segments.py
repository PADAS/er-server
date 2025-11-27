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
        filter_flag = self.context.get("filter")

        # Get subject's segments
        segments_qs = ObservationSegment.objects.filter(subject=subject).select_related("subject")

        # Apply time filters
        if since:
            segments_qs = segments_qs.filter(start_recorded_at__gte=since)
        if until:
            segments_qs = segments_qs.filter(end_recorded_at__lte=until)

        # Apply exclusion flag filter
        if filter_flag is not None:
            segments_qs = segments_qs.filter(exclusion_flags=filter_flag)

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
