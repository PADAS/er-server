import logging
import re
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework import serializers

from buoy.constants import (
    DEPLOYMENT_TYPE_CHOICES,
    DEVICE_DEPLOYMENT_STATUS_CHOICES,
    DEVICES_KEY,
    DISPLAY_ID_KEY,
    GEAR_TYPE_SINGLE,
    GEAR_TYPE_TRAWL,
    POSITIONING_TYPE_CHOICES,
    POSITIONING_TYPE_GPS,
    RELEASE_TYPE_CHOICES,
)
from observations import models
from observations.models import SubjectSource

logger = logging.getLogger(__name__)


class GeoLocationSerializer(serializers.Serializer):
    latitude = serializers.FloatField(
        required=True,
    )
    longitude = serializers.FloatField(
        required=True,
    )

    def validate_latitude(self, value):
        """Validate latitude is within valid range."""
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90 degrees")
        return value

    def validate_longitude(self, value):
        """Validate longitude is within valid range."""
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180 degrees")
        return value


class GearDeviceCreateSerializer(serializers.Serializer):
    mfr_device_id = serializers.CharField(max_length=100, required=True)
    mfr_id = serializers.CharField(max_length=100, required=True)
    last_deployed = serializers.DateTimeField(
        required=True,
    )
    last_updated = serializers.DateTimeField(
        required=True,
    )
    device_status = serializers.ChoiceField(
        choices=DEVICE_DEPLOYMENT_STATUS_CHOICES,
        required=True,
    )
    positioning_type = serializers.ChoiceField(
        choices=POSITIONING_TYPE_CHOICES,
        default=POSITIONING_TYPE_GPS,
        required=False,
    )
    release_type = serializers.ChoiceField(
        choices=RELEASE_TYPE_CHOICES,
        required=False,
    )
    location = GeoLocationSerializer(required=True)
    device_additional_data = serializers.JSONField(
        required=False,
    )
    device_pgn_data = serializers.JSONField(
        required=False,
    )

    def validate_mfr_device_id(self, value):
        """Validate manufacturer device ID is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Manufacturer device ID cannot be empty")
        return value.strip()

    def validate_mfr_id(self, value):
        """Validate manufacturer ID is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Manufacturer ID cannot be empty")
        return value.strip()

    def validate_last_deployed(self, value):
        if value:
            now = datetime.now(timezone.utc)
            if value > now:
                raise serializers.ValidationError("Device deployment date cannot be in the future")

        return value

    def validate_last_updated(self, value):
        """Validate device last updated date."""
        if value:
            now = datetime.now(timezone.utc)
            if value > now:
                raise serializers.ValidationError("Device last updated date cannot be in the future")

        return value

    def validate(self, attrs):
        deploy_date = attrs.get("last_deployed")
        updated_date = attrs.get("last_updated")

        if deploy_date and updated_date and updated_date < deploy_date:
            raise serializers.ValidationError({"last_updated": "Last updated date cannot be before deployment date"})

        return super().validate(attrs)


class GearCreateSerializer(serializers.Serializer):
    set_id = serializers.CharField(max_length=100, required=False)
    set_display_id = serializers.CharField(max_length=100, required=False)
    vessel_id = serializers.CharField(max_length=100, required=False)
    mfr_set_id = serializers.CharField(max_length=100, required=False)
    owner_id = serializers.CharField(max_length=100, required=True)
    permit_number = serializers.CharField(max_length=100, required=False)
    deployment_type = serializers.ChoiceField(choices=DEPLOYMENT_TYPE_CHOICES, required=True)
    devices_in_set = serializers.IntegerField(required=False)
    trawl_path = serializers.ListField(child=GeoLocationSerializer(), required=False)
    last_updated = serializers.DateTimeField(required=False)
    initial_deployment_date = serializers.DateTimeField(required=False)  # Conditionally required
    set_additional_data = serializers.JSONField(required=False)
    devices = GearDeviceCreateSerializer(many=True, required=True)

    def validate_owner_id(self, value):
        """Validate owner_id is not empty and has valid format."""
        if not value or not value.strip():
            raise serializers.ValidationError("Owner ID cannot be empty")
        return value.strip()

    def validate_devices_in_set(self, value):
        """Validate devices_in_set is a positive integer."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("devices_in_set must be a positive integer")
        return value

    def validate_initial_deployment_date(self, value):
        """Validate deployment date is not too far in the past or future."""
        if value:
            now = datetime.now(timezone.utc)
            if value > now:
                raise serializers.ValidationError("Initial deployment date cannot be in the future")
        return value

    def validate(self, attrs):
        """
        Cross-field validation for gear creation.
        Also, if set_id is not provided, try to infer it from devices using _get_gearset_id
        and add it to the validated data.
        """
        devices = attrs.get("devices", [])
        devices_in_set = attrs.get("devices_in_set")

        if devices_in_set is not None and len(devices) != devices_in_set:
            raise serializers.ValidationError(
                {
                    "devices_in_set": (
                        f"devices_in_set ({devices_in_set}) must match the actual number of devices ({len(devices)})"
                    )
                }
            )

        if not devices:
            raise serializers.ValidationError({"devices": "At least one device must be provided"})

        if not attrs.get("set_id"):
            inferred_set_id = self._get_gearset_id(attrs, devices)
            if inferred_set_id:
                attrs["set_id"] = inferred_set_id
            else:
                attrs["set_id"] = str(uuid4())

        if not attrs.get("set_display_id"):
            attrs["set_display_id"] = attrs["set_id"]

        # Check if this is a new gear set or an update
        set_id = attrs.get("set_id")
        subject = models.Subject.objects.filter(name=set_id).first() if set_id else None

        # initial_deployment_date is required only for new gear sets
        if not subject and not attrs.get("initial_deployment_date"):
            raise serializers.ValidationError(
                {"initial_deployment_date": "This field is required when creating a new gear set"}
            )

        # Additional device/subject/source validations moved from the view
        # Ensure per-device state transitions are valid (deployed <-> hauled)
        devices = attrs.get("devices", [])

        device_errors = {}
        for idx, device in enumerate(devices):
            mfr_id = device.get("mfr_device_id")
            # Build a Point to compare locations if needed
            loc = device.get("location") or {}
            device_location = None
            if "longitude" in loc and "latitude" in loc:
                device_location = models.Point(loc["longitude"], loc["latitude"])

            # Try to find an existing Source/SubjectSource for checks. Absence is valid for deployments
            source = models.Source.objects.filter(manufacturer_id=mfr_id).first()
            subject_source = None
            if subject and source:
                subject_source = SubjectSource.objects.filter(subject=subject, source=source).first()

            # Default assigned range sentinel
            default_lower, default_upper = models.DEFAULT_ASSIGNED_RANGE

            # If device is being deployed, ensure we're not redeploying same device at same location
            if device.get("device_status") == "deployed":
                if subject_source is not None:
                    current_assigned_range = subject_source.assigned_range
                    if current_assigned_range is not None and current_assigned_range.lower != default_lower:
                        # If it's already deployed at same location, collect error
                        device_latitude = subject_source.location.y if subject_source.location else None
                        device_longitude = subject_source.location.x if subject_source.location else None
                        current_latitude = device_location.y if device_location is not None else None
                        current_longitude = device_location.x if device_location is not None else None
                        if device_location is not None and (device_latitude, device_longitude) == (
                            current_latitude,
                            current_longitude,
                        ):
                            device_errors.setdefault(idx, []).append(
                                f"Device {subject_source.source.manufacturer_id} is already deployed at this location."
                            )

            # If device is being hauled, ensure it's currently deployed
            else:
                # If there's an existing subject_source, ensure it hasn't already been hauled
                if subject_source is not None:
                    current_assigned_range = subject_source.assigned_range
                    if current_assigned_range is not None and current_assigned_range.upper != default_upper:
                        device_errors.setdefault(idx, []).append(
                            f"Device {subject_source.source.manufacturer_id} is already hauled"
                        )
                # If we expect to haul but there's no subject_source (or no subject/source) that's invalid
                if subject_source is None:
                    device_errors.setdefault(idx, []).append(f"Device {mfr_id} is not deployed, cannot be hauled.")

        if device_errors:
            raise serializers.ValidationError({"devices": device_errors})

        return super().validate(attrs)

    def _get_gearset_id(self, gearset_data, devices_info):
        """
        Determine the gearset ID based on provided data.
        1. If set_id is provided in gearset_data, use that.
        2. Else, find a Subject that is active and has SubjectSource for all device_ids in devices_info.
        3. If neither is available, return None to use the previously generated UUID.
        """
        set_id = gearset_data.get("set_id")
        if set_id:
            return set_id

        device_ids = [d.get("mfr_device_id") for d in devices_info if d.get("mfr_device_id")]
        if device_ids:
            # Find Subjects that are active and have SubjectSource for all device_ids
            subjects_qs = (
                SubjectSource.objects.filter(source__manufacturer_id__in=device_ids, subject__is_active=True)
                .select_related("subject")
                .values("subject_id")
            )
            subject_ids = [s["subject_id"] for s in subjects_qs]
            # Count how many times each subject_id appears
            subject_id_counts = Counter(subject_ids)
            # The subject_id that appears for all device_ids is the gearset
            for subject_id, count in subject_id_counts.items():
                if count == len(device_ids):
                    # Get the subject name
                    subject = models.Subject.objects.filter(id=subject_id).first()
                    if subject:
                        return str(subject.name)
        return None


class GearSerializer(serializers.ModelSerializer):
    """ModelSerializer that serializes a SubjectSource and returns
    a gear representation.

    It mirrors the structure:

    {
        "id": "uuid",
        "display_id": "string",
        "status": "deployed | hauled",
        "last_updated": "isoformat",
        "devices": [
            {
                "device_id": "string",
                "source_id": "uuid",
                "label": "string",
                "location": {
                    "latitude": float,
                    "longitude": float
                },
                "last_updated": "isoformat",
                "last_deployed": "isoformat"
            }
        ],
        "type": "single | trawl",
        "manufacturer": "string"
    }
    """

    id = serializers.UUIDField(source="subject.id")
    display_id = serializers.SerializerMethodField()
    last_updated = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    devices = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    manufacturer = serializers.SerializerMethodField()

    def get_last_updated(self, obj):
        """Get last_updated from Subject's additional field, fallback to updated_at."""
        if subject := obj.subject:
            additional = subject.additional or {}
            if "last_updated" in additional:
                # Parse ISO format datetime string from additional field
                last_updated_str = additional["last_updated"]
                if isinstance(last_updated_str, str):
                    from django.utils.dateparse import parse_datetime

                    return parse_datetime(last_updated_str)
                return last_updated_str
            return subject.updated_at
        raise serializers.ValidationError("Subject is missing for SubjectSource")

    def get_display_id(self, obj):
        if subject := obj.subject:
            if DISPLAY_ID_KEY in subject.additional:
                return subject.additional[DISPLAY_ID_KEY]
            return subject.name
        raise serializers.ValidationError("Subject is missing for SubjectSource")

    def get_status(self, obj):
        if subject := obj.subject:
            return "deployed" if subject.is_active else "hauled"
        raise serializers.ValidationError("Subject is missing for SubjectSource")

    def get_manufacturer(self, obj):
        if subject := obj.subject:
            additional = subject.additional or {}
            manufacturer = additional.get("manufacturer")
            if manufacturer:
                return manufacturer

        provider_key = obj.source.provider.provider_key
        if match := re.match(r"^gundi_(.+?)_[0-9a-f-]+$", provider_key):
            return match.group(1)
        return provider_key

    def get_devices(self, obj):
        if subject := obj.subject:
            devices = []
            now = datetime.now(timezone.utc)

            # Build base query for related subject sources
            related_subject_sources_query = (
                models.SubjectSource.objects.filter(subject__name=subject.name)
                .annotate(lower=Lower("assigned_range"))
                .exclude(
                    lower=datetime.min.replace(tzinfo=now.tzinfo)
                )  # This prevents including sources that didn't have the lower bound set i.e. deployed
                .select_related("source", "source__provider")
            )

            if subject.is_active:
                # For ACTIVE subjects: Get only currently deployed sources (within current time range)
                related_subject_sources = related_subject_sources_query.filter(assigned_range__contains=now)
            else:
                # For INACTIVE subjects: Get all historical sources (regardless of time range)
                related_subject_sources = related_subject_sources_query

            for idx, subject_source in enumerate(related_subject_sources):
                if subject_source.source:
                    device_id = subject_source.source.manufacturer_id
                    # Use prefetched LatestObservationSource data instead of making individual queries
                    # This prevents N+1 query problem when serializing multiple gears
                    latest_obs_source = subject_source.source.last_observation_sources.first()
                    if latest_obs_source and latest_obs_source.observation:
                        observation = latest_obs_source.observation
                        location = {"latitude": observation.location.y, "longitude": observation.location.x}
                    else:
                        location = {"latitude": None, "longitude": None}

                    # Get last_updated from Source's additional field, fallback to updated_at
                    source_additional = subject_source.source.additional or {}
                    if "last_updated" in source_additional:
                        last_updated_str = source_additional["last_updated"]
                        if isinstance(last_updated_str, str):
                            from django.utils.dateparse import parse_datetime

                            device_last_updated = parse_datetime(last_updated_str)
                        else:
                            device_last_updated = last_updated_str
                    else:
                        device_last_updated = subject_source.source.updated_at

                    device = {
                        "device_id": device_id,
                        "source_id": str(subject_source.source.id),
                        "label": chr(97 + idx),  # 'a', 'b', 'c', etc.
                        "location": location,
                        "last_updated": device_last_updated,
                        "last_deployed": subject_source.assigned_range.lower,
                    }
                    devices.append(device)

            return devices
        raise serializers.ValidationError("Subject is missing for SubjectSource")

    def get_type(self, obj):
        if subject := obj.subject:
            additional = subject.additional or {}
            devices = additional.get(DEVICES_KEY, [])
            return GEAR_TYPE_TRAWL if len(devices) > 1 else GEAR_TYPE_SINGLE
        raise serializers.ValidationError("Subject is missing for SubjectSource")

    class Meta:
        model = models.SubjectSource
        fields = ("id", "display_id", "status", "devices", "type", "manufacturer", "last_updated")
