import logging
import re
from datetime import datetime, timezone

from drf_extra_fields.geo_fields import PointField

from django.db.models.functions import Lower
from rest_framework import serializers

from buoy.constants import BUOY_SUBJECT_SUBTYPE
from observations import models
from observations.serializers import SubjectRelatedField

logger = logging.getLogger(__name__)

DISPLAY_ID_KEY = "display_id"
DEVICES_KEY = "devices"
ID_KEY = "id"
STATUS_KEY = "status"
GEAR_TYPE_TRAWL = "trawl"
GEAR_TYPE_SINGLE = "single"
SUBJECT_KEY = "subject"


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

    def to_internal_value(self, data):
        if ID_KEY in data and self.read_only:
            try:
                if hasattr(data, "source"):
                    return models.SubjectSource.objects.get(id=data["id"])
                else:
                    return models.Subject.objects.get(id=data["id"])
            except (models.SubjectSource.DoesNotExist, models.Subject.DoesNotExist):
                raise serializers.ValidationError(f"Object: {data} does not exist.")
        return super().to_internal_value(data)

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
            related_sources = instance.subjectsources.all()
            if related_sources:
                provider_key = related_sources[0].source.provider.provider_key
            else:
                return "unknown"

        if provider_key:
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
        if subject.get("subject_subtype") == BUOY_SUBJECT_SUBTYPE:
            gear_rep[ID_KEY] = subject[ID_KEY]
            gear_rep[DISPLAY_ID_KEY] = subject["name"]
            gear_rep[STATUS_KEY] = "deployed" if subject["is_active"] else "hauled"
            gear_rep["last_updated"] = subject["updated_at"]

            # Get devices from related SubjectSources
            # Note: subjectsources and their sources are prefetched in the view to avoid N+1 queries
            devices = []
            minimum_active_lower_bound = datetime.min.replace(tzinfo=now.tzinfo)
            if subject["is_active"]:
                related_subject_sources = (
                    instance.subject.subjectsources.annotate(lower=Lower("assigned_range"))
                    .filter(assigned_range__contains=now)
                    .exclude(
                        lower=minimum_active_lower_bound
                    )  # This prevents including sources that didn't had the lower bound set
                )
            else:
                related_subject_sources = instance.subject.subjectsources.annotate(
                    lower=Lower("assigned_range")
                ).exclude(
                    lower=minimum_active_lower_bound
                )  # This prevents including sources that didn't had the lower bound set
            for idx, subject_source in enumerate(related_subject_sources):
                if subject_source.source:
                    device_id = subject_source.source.manufacturer_id
                    observation = models.LatestObservationSource.objects.get_latest_for_source(subject_source.source)
                    additional = subject_source.source.additional or {}
                    device = {
                        "device_id": device_id,
                        "source_id": str(subject_source.source.id),
                        "label": self._idx_to_device_label(idx),
                        "location": {"latitude": observation.location.y, "longitude": observation.location.x},
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
