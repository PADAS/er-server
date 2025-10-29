import logging
import re
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from drf_extra_fields.geo_fields import PointField

from django.db.models.functions import Lower
from rest_framework import serializers

from buoy.constants import (
    BUOY_GEAR_SUBJECT_SUBTYPE,
    DEPLOYMENT_TYPE_CHOICES,
    DEVICE_DEPLOYMENT_STATUS_CHOICES,
    DEVICES_KEY,
    DISPLAY_ID_KEY,
    GEAR_TYPE_SINGLE,
    GEAR_TYPE_TRAWL,
    ID_KEY,
    POSITIONING_TYPE_CHOICES,
    POSITIONING_TYPE_GPS,
    RELEASE_TYPE_CHOICES,
    SOURCE_TYPE,
    STATUS_KEY,
    TRAP_DEPLOYED,
    TRAP_RETRIEVED,
)
from observations import models
from observations.models import SubjectSource
from observations.serializers import SubjectRelatedField

logger = logging.getLogger(__name__)


class GearSerializer(serializers.Serializer):
    id = serializers.UUIDField(
        required=False,
    )
    location = PointField(required=False)
    subject = SubjectRelatedField()

    additional_fields = ("devices", "additional")

    class Meta:
        model = models.SubjectSource
        fields = ("id", "assigned_range", "source", "subject", "additional", "location")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def simple_mode(self):
        return self.context.get("simple_mode", False)

    def get_type(self, subject):
        additional = subject.get("additional", {})
        if DEVICES_KEY not in additional or len(additional[DEVICES_KEY]) == 0:
            raise serializers.ValidationError(f"Subject {subject['id']} does not have additional devices information.")

        return GEAR_TYPE_TRAWL if len(subject["additional"][DEVICES_KEY]) > 1 else GEAR_TYPE_SINGLE

    def get_display_id(self, subject):
        if DISPLAY_ID_KEY in subject.get("additional", {}):
            return subject["additional"][DISPLAY_ID_KEY]
        return subject["name"]

    def _idx_to_device_label(self, idx):
        """
        Convert an index to a device label.
        1. a, 2. b, 3. c, etc.
        """
        return chr(97 + idx)

    def get_source_provider_standardized_name(self, instance):
        """
        Get the standardized name of the source provider.
        """
        if hasattr(instance, "source"):
            provider_key = instance.source.provider.provider_key
        else:
            if related_sources := instance.subjectsources.first():
                provider_key = related_sources.source.provider.provider_key
            else:
                return "unknown"

        if match := re.match(r"^gundi_(.+?)_[0-9a-f-]+$", provider_key):
            return match.group(1)

        return provider_key

    def to_representation(self, instance):
        if isinstance(instance, models.Subject):
            subject = {
                "id": str(instance.id),
                "name": instance.name,
                "subject_subtype": instance.subject_subtype.value if instance.subject_subtype else None,
                "is_active": instance.is_active,
                "updated_at": instance.updated_at,
                "additional": instance.additional or {},
            }
            if self.simple_mode:
                return {
                    "id": subject["id"],
                    "display_id": subject["name"],
                    "status": "deployed" if subject["is_active"] else "hauled",
                    "last_updated": subject["updated_at"],
                }
            related_subjectsource = instance.subjectsources.first()
            if not related_subjectsource:
                raise serializers.ValidationError("Subject has no associated sources")
            instance = related_subjectsource

        rep = super(GearSerializer, self).to_representation(instance)
        subject = rep["subject"]
        now = datetime.now(timezone.utc)

        if not isinstance(subject, dict):
            raise serializers.ValidationError("Subject must be a dictionary")

        gear_rep = dict()

        # Handle ropeless_buoy_gearset differently
        if subject.get("subject_subtype") == BUOY_GEAR_SUBJECT_SUBTYPE:
            gear_rep[ID_KEY] = subject[ID_KEY]
            gear_rep[DISPLAY_ID_KEY] = subject["name"]
            gear_rep[STATUS_KEY] = "deployed" if subject["is_active"] else "hauled"
            gear_rep["last_updated"] = subject["updated_at"]

            # Get devices from related SubjectSources
            # Note: subjectsources and their sources are prefetched in the view to avoid N+1 queries
            devices = []
            minimum_active_lower_bound = datetime.min.replace(tzinfo=now.tzinfo)

            # Build base query for related subject sources
            related_subject_sources_query = (
                models.SubjectSource.objects.filter(subject__name=subject["name"])
                .annotate(lower=Lower("assigned_range"))
                .exclude(
                    lower=minimum_active_lower_bound
                )  # This prevents including sources that didn't have the lower bound set i.e. deployed
                .select_related("source", "source__provider")
            )

            if subject["is_active"]:
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

                    device = {
                        "device_id": device_id,
                        "source_id": str(subject_source.source.id),
                        "label": self._idx_to_device_label(idx),
                        "location": location,
                        "last_updated": subject_source.source.updated_at,
                        "last_deployed": subject_source.assigned_range.lower,
                    }
                    devices.append(device)

            gear_rep[DEVICES_KEY] = devices
            gear_rep["type"] = GEAR_TYPE_TRAWL if len(devices) > 1 else GEAR_TYPE_SINGLE
            gear_rep["manufacturer"] = self.get_source_provider_standardized_name(instance)
        else:
            # Original logic for other subject subtypes
            gear_rep[ID_KEY] = subject[ID_KEY]
            gear_rep[STATUS_KEY] = "deployed" if subject["is_active"] else "hauled"
            gear_rep["last_updated"] = subject["updated_at"]
            # TODO: add last_change_time
            additional = subject.get("additional")
            if additional:
                gear_rep[DISPLAY_ID_KEY] = self.get_display_id(subject)
                if DEVICES_KEY in additional:
                    gear_rep["type"] = self.get_type(subject)
                    gear_rep[DEVICES_KEY] = subject["additional"][DEVICES_KEY]
            else:
                gear_rep[DISPLAY_ID_KEY] = subject["name"]
                # TODO: return 500 internal server error with this detail
                gear_rep["type"] = "Error: no device information"
                gear_rep[DEVICES_KEY] = []
            gear_rep["manufacturer"] = self.get_source_provider_standardized_name(instance)

        return gear_rep


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
    device_id = serializers.CharField(max_length=255, required=False)
    mfr_device_id = serializers.CharField(max_length=255, required=True)
    mfr_id = serializers.CharField(max_length=255, required=True)
    device_initial_deploy_date = serializers.DateTimeField(
        required=True,
    )
    device_last_updated_date = serializers.DateTimeField(
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

    def validate_device_initial_deploy_date(self, value):
        if value:
            now = datetime.now(timezone.utc)
            if value > now:
                raise serializers.ValidationError("Device deployment date cannot be in the future")

        return value

    def validate_device_last_updated_date(self, value):
        """Validate device last updated date."""
        if value:
            now = datetime.now(timezone.utc)
            if value > now:
                raise serializers.ValidationError("Device last updated date cannot be in the future")

        return value

    def validate(self, attrs):
        deploy_date = attrs.get("device_initial_deploy_date")
        updated_date = attrs.get("device_last_updated_date")

        if deploy_date and updated_date and updated_date < deploy_date:
            raise serializers.ValidationError(
                {"device_last_updated_date": "Last updated date cannot be before deployment date"}
            )

        return super().validate(attrs)


class GearCreateSerializer(serializers.Serializer):
    set_id = serializers.CharField(max_length=255, required=False)
    set_display_id = serializers.CharField(max_length=255, required=False)
    vessel_id = serializers.CharField(max_length=255, required=False)
    mfr_set_id = serializers.CharField(max_length=255, required=False)
    owner_id = serializers.CharField(max_length=255, required=True)
    permit_number = serializers.CharField(max_length=255, required=False)
    deployment_type = serializers.ChoiceField(choices=DEPLOYMENT_TYPE_CHOICES, required=True)
    devices_in_set = serializers.IntegerField(required=False)
    trawl_path = serializers.ListField(child=GeoLocationSerializer(), required=False)
    last_updated_date = serializers.DateTimeField(required=False)
    initial_deployment_date = serializers.DateTimeField(required=True)
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

        deployed_devices = [d for d in devices if d.get("device_status") == "deployed"]
        hauled_devices = [d for d in devices if d.get("device_status") == "hauled"]

        if deployed_devices and hauled_devices:
            raise serializers.ValidationError(
                {"devices": "All devices in a gear set should have the same deployment status"}
            )

        return super().validate(attrs)

    def get_device_label(self, position_index: int):
        """Receive the position index and return a label for the device in the format A, B, C, ..., Z, AA, AB ..."""
        result = []
        while position_index > 0:
            position_index -= 1
            result.append(chr(ord("A") + (position_index % 26)))
            position_index //= 26
        return "".join(reversed(result))

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

        device_ids = [d.get("device_id") for d in devices_info if d.get("device_id")]
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

    def save(self, **kwargs):
        observations = []
        gearset_data = self.validated_data
        random_gear_set_id = str(uuid4())
        devices_info = self.validated_data.get("devices", [])
        gearset_id = self._get_gearset_id(gearset_data, devices_info) or random_gear_set_id
        for position_idx, device_info in enumerate(devices_info):
            is_active = device_info.get("device_status") == "deployed"
            observation = {
                "source_name": gearset_id,
                "source": device_info.get("device_id") or str(uuid4()),
                "subject_type": BUOY_GEAR_SUBJECT_SUBTYPE,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "source_type": SOURCE_TYPE,
                "location": {"lat": device_info["location"]["latitude"], "lon": device_info["location"]["longitude"]},
                "additional": {
                    "event_type": TRAP_DEPLOYED if is_active else TRAP_RETRIEVED,
                    "raw": self.validated_data,
                },
            }
            observations.append(observation)

        return observations

    class Meta(GearSerializer.Meta):
        fields = (
            "set_id",
            "vessel_id",
            "mfr_set_id",
            "owner_id",
            "set_display_id",
            "permit_number",
            "deployment_type",
            "trawl_path",
        )
