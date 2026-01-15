import logging
import re
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from django.db.models.functions import Lower
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from buoy.constants import (
    DEPLOYMENT_TYPE_CHOICES,
    DEVICE_DEPLOYMENT_STATUS_CHOICES,
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
    device_id = serializers.UUIDField(required=True)
    mfr_device_id = serializers.CharField(max_length=100, required=False)
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
    recorded_at = serializers.DateTimeField(required=False)

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
        # Use device_id as mfr_device_id if not provided
        if not attrs.get("mfr_device_id"):
            attrs["mfr_device_id"] = str(attrs.get("device_id"))

        return super().validate(attrs)


class GearCreateSerializer(serializers.Serializer):
    set_id = serializers.UUIDField(required=False)
    mfr_set_id = serializers.CharField(max_length=100, required=False)
    set_display_id = serializers.CharField(max_length=100, required=False)
    manufacturer_name = serializers.CharField(max_length=100, required=True)
    owner_id = serializers.CharField(max_length=100, required=False)
    vessel_id = serializers.CharField(max_length=100, required=False)
    permit_number = serializers.CharField(max_length=100, required=False)
    deployment_type = serializers.ChoiceField(choices=DEPLOYMENT_TYPE_CHOICES, required=True)
    devices_in_set = serializers.IntegerField(required=False)
    # Disable trawl_path for now, until the requirements are clearer
    # trawl_path = serializers.ListField(child=GeoLocationSerializer(), required=False)
    last_updated = serializers.DateTimeField(required=False)
    initial_deployment_date = serializers.DateTimeField(required=False)  # Conditionally required
    set_additional_data = serializers.JSONField(required=False)
    devices = GearDeviceCreateSerializer(many=True, required=True)

    def validate_manufacturer_name(self, value):
        """Validate manufacturer_name corresponds to an existing SubjectGroup."""
        if not value or not value.strip():
            raise serializers.ValidationError("Manufacturer name cannot be empty")

        value = value.strip()

        # Check if SubjectGroup exists
        try:
            subject_group = models.SubjectGroup.objects.get(name=value)
        except models.SubjectGroup.DoesNotExist:
            raise serializers.ValidationError(
                f"SubjectGroup with name '{value}' does not exist. "
                "Please contact your administrator to create this manufacturer group."
            )

        # Check if user has permission to add subjects to this SubjectGroup
        # Get user from request context (standard DRF pattern)
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError(
                "Request context is required for validation. "
                "Ensure the serializer is called with request in context."
            )

        user = request.user

        # Superusers can create gears in any SubjectGroup
        if not user.is_superuser:
            # Check if user has permission to this SubjectGroup
            user_permission_sets = user.get_all_permission_sets() if hasattr(user, "get_all_permission_sets") else []
            allowed_subject_groups = models.SubjectGroup.objects.filter(permission_sets__in=user_permission_sets)

            if subject_group not in allowed_subject_groups:
                raise serializers.ValidationError(
                    f"You do not have permission to create gears in SubjectGroup '{value}'. "
                    "Please contact your administrator to request access."
                )

        return value

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
            if not inferred_set_id:
                raise serializers.ValidationError(
                    {"set_id": "Cannot determine set_id. Please provide either set_id or mfr_set_id."}
                )
            attrs["set_id"] = inferred_set_id

        # mfr_set_id defaults to set_id
        if not attrs.get("mfr_set_id"):
            attrs["mfr_set_id"] = str(attrs["set_id"])

        # set_display_id defaults to mfr_set_id
        if not attrs.get("set_display_id"):
            attrs["set_display_id"] = attrs["mfr_set_id"]

        # Check if this is a new gear set or an update
        set_id = attrs.get("set_id")
        subject = models.Subject.objects.filter(id=set_id).first() if set_id else None

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
            device_id = str(device.get("device_id"))
            # Build a Point to compare locations if needed
            loc = device.get("location") or {}
            device_location = None
            if "longitude" in loc and "latitude" in loc:
                device_location = models.Point(loc["longitude"], loc["latitude"])

            # Try to find an existing Source/SubjectSource for checks. Absence is valid for deployments
            source = models.Source.objects.filter(id=device_id).first()
            subject_source = None
            if subject and source:
                subject_source = SubjectSource.objects.filter(subject=subject, source=source).first()

            # If device is being deployed, ensure we're not redeploying same device at same location
            if device.get("device_status") == "deployed":
                if subject_source is not None:
                    # Check if device is currently deployed by checking if has assigned lower range (deployment time)
                    # and that the current time is within the assigned range (i.e., is_current) considering that the default
                    # upper bound is datetime.max and therefore the device is still deployed.
                    is_currently_deployed = subject_source.has_assigned_lower_range and subject_source.is_current
                    if is_currently_deployed:
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
                    is_currently_deployed = subject_source.has_assigned_lower_range and subject_source.is_current
                    if not is_currently_deployed:
                        device_errors.setdefault(idx, []).append(
                            f"Device {subject_source.source.manufacturer_id} is already hauled"
                        )
                # If we expect to haul but there's no subject_source (or no subject/source) that's invalid
                if subject_source is None:
                    device_errors.setdefault(idx, []).append(f"Device {device_id} is not deployed, cannot be hauled.")

        if device_errors:
            raise serializers.ValidationError({"devices": device_errors})

        return super().validate(attrs)

    def _get_gearset_id(self, gearset_data, devices_info):
        """
        Determine the gearset ID based on provided data.
        1. If set_id is provided in gearset_data, use that.
        2. Else if mfr_set_id is provided, look up Subject by name (Subject.name == mfr_set_id).
        3. Else, find a Subject that is active and has SubjectSource for all device_ids in devices_info.
        4. If none of the above work and mfr_set_id is provided, generate a new UUID (new subject will be created).
        5. Otherwise, return None (will trigger validation error).
        """
        set_id = gearset_data.get("set_id")
        if set_id:
            return set_id

        mfr_set_id = gearset_data.get("mfr_set_id")

        # Try to find existing Subject by mfr_set_id (stored as Subject.name)
        if mfr_set_id:
            subject = models.Subject.objects.filter(name=mfr_set_id).first()
            if subject:
                return subject.id

        # Try to find Subject by device_ids
        device_ids = [str(d.get("device_id")) for d in devices_info if d.get("device_id")]
        if device_ids:
            # Find Subjects that are active and have SubjectSource for all device_ids (Source.id)
            subjects_qs = (
                SubjectSource.objects.filter(source__id__in=device_ids, subject__is_active=True)
                .select_related("subject")
                .values("subject_id")
            )
            subject_ids = [s["subject_id"] for s in subjects_qs]
            # Count how many times each subject_id appears
            subject_id_counts = Counter(subject_ids)
            # The subject_id that appears for all device_ids is the gearset
            for subject_id, count in subject_id_counts.items():
                if count == len(device_ids):
                    return subject_id

        # If we have mfr_set_id but didn't find existing subject, generate new UUID for creation
        if mfr_set_id:
            return uuid4()

        # No way to determine set_id
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
                "mfr_device_id": "string",
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

                    last_updated = parse_datetime(last_updated_str)
                else:
                    last_updated = last_updated_str
            else:
                last_updated = subject.updated_at

            if hasattr(last_updated, "isoformat"):
                return last_updated.isoformat()
            return last_updated
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
            # First, try to get manufacturer from Subject's additional field (new approach)
            additional = subject.additional or {}
            manufacturer = additional.get("manufacturer")
            if manufacturer:
                return manufacturer

            # Second, try to get from SubjectGroup name
            # Get the first SubjectGroup the subject belongs to (assuming one SubjectGroup per manufacturer)
            subject_groups = subject.groups.all()
            if subject_groups.exists():
                return subject_groups.first().name

        # Fallback to provider_key for backward compatibility
        if obj.source and obj.source.provider:
            provider_key = obj.source.provider.provider_key
            if match := re.match(r"^gundi_(.+?)_[0-9a-f-]+$", provider_key):
                return match.group(1)
            return provider_key

        return "unknown"

    def get_devices(self, obj):
        if subject := obj.subject:
            devices = []
            now = datetime.now(timezone.utc)

            # Build base query for related subject sources
            related_subject_sources_query = (
                models.SubjectSource.objects.filter(subject__id=subject.id)
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
                    device_id = str(subject_source.source.id)
                    mfr_device_id = subject_source.source.manufacturer_id
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

                    # Convert to ISO format string
                    if hasattr(device_last_updated, "isoformat"):
                        device_last_updated = device_last_updated.isoformat()

                    # Convert last_deployed to ISO format string
                    last_deployed = subject_source.assigned_range.lower
                    if hasattr(last_deployed, "isoformat"):
                        last_deployed = last_deployed.isoformat()

                    device = {
                        "device_id": device_id,
                        "mfr_device_id": mfr_device_id,
                        "label": chr(97 + idx),  # 'a', 'b', 'c', etc.
                        "location": location,
                        "last_updated": device_last_updated,
                        "last_deployed": last_deployed,
                    }
                    devices.append(device)

            return devices
        raise serializers.ValidationError("Subject is missing for SubjectSource")

    def get_type(self, obj):
        devices = self.get_devices(obj)
        return GEAR_TYPE_TRAWL if len(devices) > 1 else GEAR_TYPE_SINGLE

    class Meta:
        model = models.SubjectSource
        fields = ("id", "display_id", "status", "devices", "type", "manufacturer", "last_updated")
