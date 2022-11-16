import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from psycopg2.extras import DateTimeTZRange

from django.db import IntegrityError

from buoy.constants import (
    BUOY_GEAR_SUBJECT_SUBTYPE,
    DEVICE_STATUS_DEPLOYED,
    DEVICE_STATUS_HAULED,
)
from observations import models
from observations.models import DEFAULT_ASSIGNED_RANGE, EMPTY_POINT
from utils.json import ExtendedJSONEncoder

logger = logging.getLogger(__name__)

# Offset added to haul time for assigned_range upper bound.
# Range queries are inclusive of lower bound, exclusive of upper bound,
# so we add padding to ensure the haul observation is included in the range.
HAUL_TIME_OFFSET = timedelta(seconds=1)


class BuoyService:
    """Service encapsulating buoy/gear business logic used by views.

    Responsibilities:
    - create Subject if missing
    - create Observations for device events
    - create/update SubjectSource assigned ranges and locations
    - update Subject active state when all devices are hauled
    """

    @staticmethod
    def _make_serializable(data):
        """Convert data to a JSON-serializable format using ExtendedJSONEncoder."""
        return json.loads(json.dumps(data, cls=ExtendedJSONEncoder))

    @staticmethod
    def process_gearset(validated_data: dict, user) -> Tuple[models.Subject, List[models.Observation]]:
        """Process a validated gearset payload.

        Args:
            validated_data (dict): validated serializer data for the gearset
            user: User instance used to determine which SubjectGroup the gear belongs to

        Returns:
            tuple: (Subject instance, list of created Observation instances)
        """
        set_id = validated_data.get("set_id")  # This is now a UUID
        mfr_set_id = str(validated_data.get("mfr_set_id"))
        set_display_id = str(validated_data.get("set_display_id"))
        set_additional_data = validated_data.get("set_additional_data", {})
        manufacturer_name = validated_data.get("manufacturer_name")
        devices = validated_data.get("devices", [])
        provider_key = models.escape_provider_name(manufacturer_name)

        # Find SubjectGroup by manufacturer_name
        # Note: manufacturer_name should already be validated in the serializer
        try:
            subject_group = models.SubjectGroup.objects.get(name=manufacturer_name)
        except models.SubjectGroup.DoesNotExist:
            # This should not happen if serializer validation passed, but handle it anyway
            raise ValueError(f"SubjectGroup with name '{manufacturer_name}' does not exist")

        provider = models.SourceProvider.objects.create_provider(
            provider_key=provider_key, display_name=manufacturer_name
        )

        # Ensure subject subtype exists for buoy gear
        subject_subtype = None
        try:
            subject_subtype = models.SubjectSubType.objects.get(value=BUOY_GEAR_SUBJECT_SUBTYPE)
        except models.SubjectSubType.DoesNotExist:
            # If subtype not present, proceed without setting it (maintain backward compatibility)
            subject_subtype = None

        # Build additional dict for Subject, starting with set_additional_data
        additional = set_additional_data.copy() if set_additional_data else {}

        # Set display_id and manufacturer_name in additional
        if set_display_id:
            additional["display_id"] = set_display_id

        # Store manufacturer_name in additional for backward compatibility
        additional["manufacturer"] = manufacturer_name

        additional = BuoyService._make_serializable(additional)

        # Build defaults with name (mfr_set_id) and additional
        subject_defaults = {"name": mfr_set_id, "additional": additional} if additional else {"name": mfr_set_id}

        # Create or get Subject using set_id as the primary key
        if subject_subtype is not None:
            subject, created = models.Subject.objects.get_or_create(
                id=set_id, subject_subtype=subject_subtype, defaults=subject_defaults
            )
        else:
            subject, created = models.Subject.objects.get_or_create(id=set_id, defaults=subject_defaults)

        # Add subject to the SubjectGroup if not already a member
        if not subject.groups.filter(id=subject_group.id).exists():
            subject.groups.add(subject_group)

        # Ensure name, display_id and manufacturer are set/updated when provided
        subject_changed = False

        # Update name (mfr_set_id) if it's different
        if mfr_set_id and subject.name != mfr_set_id:
            subject.name = mfr_set_id
            subject_changed = True

        # Update additional fields
        if set_display_id or manufacturer_name or set_additional_data:
            subj_additional = subject.additional or {}

            # Merge set_additional_data first - only if non-empty and introduces changes
            if set_additional_data:
                changes = any(subj_additional.get(k) != v for k, v in set_additional_data.items())
                if changes:
                    subj_additional.update(set_additional_data)
                    subject_changed = True

            if set_display_id and subj_additional.get("display_id") != set_display_id:
                subj_additional["display_id"] = set_display_id
                subject_changed = True
            if manufacturer_name and subj_additional.get("manufacturer") != manufacturer_name:
                subj_additional["manufacturer"] = manufacturer_name
                subject_changed = True
            if subject_changed:
                subject.additional = subj_additional

        # Make a JSON-serializable copy of validated_data for storing in DB JSON fields
        serializable_validated = BuoyService._make_serializable(validated_data)

        observations = []

        # Store last_updated in Subject's additional field if provided
        if validated_data.get("last_updated"):
            subj_additional = subject.additional or {}
            subj_additional["last_updated"] = BuoyService._make_serializable(validated_data["last_updated"])
            subject.additional = subj_additional
            subject_changed = True

        if subject_changed:
            subject.save()

        for device_data in devices:
            # Use device_id as Source.id and mfr_device_id as manufacturer_id
            device_id = str(device_data["device_id"])
            mfr_device_id = device_data.get("mfr_device_id")

            # Handle null/missing location - Edgetech may send location object with null lat/lon
            device_location_data = device_data.get("location")
            if (
                device_location_data
                and device_location_data.get("longitude") is not None
                and device_location_data.get("latitude") is not None
            ):
                device_location = models.Point(device_location_data["longitude"], device_location_data["latitude"])
            else:
                device_location = EMPTY_POINT
                logger.info(f"Device {device_id} (mfr_device_id: {mfr_device_id}) has no location data")

            if not device_data.get("recorded_at"):
                logger.warning(
                    f"recorded_at not provided for device {device_id}, mfr_device_id: {mfr_device_id}, using current time"
                )
                recorded_at = datetime.now(timezone.utc)
            else:
                recorded_at = device_data.get("recorded_at")

            # Get or create Source. Prefer lookup by id (device_id) to avoid duplicate key when
            # the same device was previously created under a different provider (e.g. after
            # changing how provider is set). When reusing an existing source by id, we do not
            # change its provider or other identity fields.
            # The unique constraint is on (das_tenant, provider, manufacturer_id), not on id.
            source = models.Source.objects.filter(id=device_id).first()
            if source is not None:
                created = False
                # Leave source.provider (and manufacturer_id) unchanged; do not overwrite.
            else:
                try:
                    if provider:
                        source, created = models.Source.objects.get_or_create(
                            provider=provider,
                            manufacturer_id=mfr_device_id,
                            defaults={"id": device_id},
                        )
                    else:
                        source, created = models.Source.objects.get_or_create(
                            manufacturer_id=mfr_device_id,
                            defaults={"id": device_id},
                        )
                except IntegrityError:
                    # Race: another request created a Source with this id; fetch it.
                    source = models.Source.objects.get(id=device_id)

            # Store last_updated in Source's additional field if provided
            if device_data.get("last_updated"):
                source_additional = source.additional or {}
                source_additional["last_updated"] = BuoyService._make_serializable(device_data["last_updated"])
                source.additional = source_additional
                source.save()

            # Store the validated payload as the raw field for traceability
            observation = models.Observation.objects.create(
                source=source,
                location=device_location,
                recorded_at=recorded_at,
                additional={"raw": serializable_validated},
            )
            observations.append(observation)

            subject_source, subject_source_created = models.SubjectSource.objects.get_or_create(
                subject=subject, source=source
            )

            if device_data.get("device_status") == DEVICE_STATUS_DEPLOYED:
                assigned_range = DateTimeTZRange(lower=recorded_at, upper=DEFAULT_ASSIGNED_RANGE[1])
            else:
                # For haul events we expect subject_source to have a lower bound already set
                if subject_source_created:
                    logger.warning(
                        f"SubjectSource created for {subject.name} and {source.manufacturer_id} but device status is {device_data.get('device_status')}, the assigned_range lower bound will be the default min time"
                    )
                assigned_range_upper = recorded_at + HAUL_TIME_OFFSET if recorded_at != datetime.max else recorded_at
                assigned_range = DateTimeTZRange(lower=subject_source.assigned_range.lower, upper=assigned_range_upper)

            # Only set SubjectSource.location if we have real location data (not EMPTY_POINT)
            # SubjectSource.location allows null, so None is more semantically correct for "no location"
            if device_location != EMPTY_POINT:
                subject_source.location = device_location
            else:
                subject_source.location = None
            subject_source.assigned_range = assigned_range
            subject_source.save()

        # Auto-haul: If any device in this request was hauled, automatically haul all other
        # deployed devices in the same gearset. This ensures the entire gearset is marked as
        # hauled even if the haul notification only includes a subset of devices.
        max_upper = DEFAULT_ASSIGNED_RANGE[1]
        any_device_hauled = any(device_data.get("device_status") == DEVICE_STATUS_HAULED for device_data in devices)

        if any_device_hauled:
            # Find the haul time from the first hauled device in the request
            haul_time = None
            for device_data in devices:
                if device_data.get("device_status") == DEVICE_STATUS_HAULED:
                    haul_time = device_data.get("recorded_at") or datetime.now(timezone.utc)
                    break

            # Find all SubjectSources for this Subject that are still deployed (open upper bound)
            deployed_subject_sources = models.SubjectSource.objects.filter(
                subject=subject,
                assigned_range__endswith=max_upper,
            )

            # Auto-haul each deployed SubjectSource
            for ss in deployed_subject_sources:
                assigned_range_upper = haul_time + HAUL_TIME_OFFSET if haul_time != datetime.max else haul_time
                ss.assigned_range = DateTimeTZRange(lower=ss.assigned_range.lower, upper=assigned_range_upper)
                ss.save()
                logger.info(
                    f"Auto-hauled device {ss.source.manufacturer_id} for gearset {subject.name} "
                    f"(set_id: {subject.id}) at {haul_time}"
                )

        # If all SubjectSource for the Subject are hauled, set Subject is_active to False
        # A SubjectSource is considered "hauled" if its assigned_range upper bound is not datetime.max
        # (i.e., the range has been closed). We check this instead of 'now not in assigned_range'
        # to avoid a race condition where 'now' might still be within the 1-second padding
        # added to the upper bound for recent haul events.
        assigned_ranges = models.SubjectSource.objects.filter(subject=subject).values_list("assigned_range", flat=True)
        # Only consider hauled if there are SubjectSources AND all have a closed upper bound
        all_hauled = assigned_ranges.exists() and all(ar.upper != max_upper for ar in assigned_ranges)
        if all_hauled:
            subject.is_active = False
            subject.save()

        return subject, observations
