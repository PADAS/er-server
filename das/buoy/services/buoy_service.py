import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from psycopg2.extras import DateTimeTZRange

from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE, DEVICE_STATUS_DEPLOYED
from observations import models
from observations.models import DEFAULT_ASSIGNED_RANGE
from utils.json import ExtendedJSONEncoder

logger = logging.getLogger(__name__)


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

        # Find SubjectGroup by manufacturer_name
        # Note: manufacturer_name should already be validated in the serializer
        try:
            subject_group = models.SubjectGroup.objects.get(name=manufacturer_name)
        except models.SubjectGroup.DoesNotExist:
            # This should not happen if serializer validation passed, but handle it anyway
            raise ValueError(f"SubjectGroup with name '{manufacturer_name}' does not exist")

        # Get default SourceProvider for Source creation
        try:
            provider = models.SourceProvider.objects.get(id=models.get_default_source_provider_id())
        except models.SourceProvider.DoesNotExist:
            logger.warning(f"Default SourceProvider not found, creating sources without provider reference")
            provider = None

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

            device_location = models.Point(device_data["location"]["longitude"], device_data["location"]["latitude"])
            if not device_data.get("recorded_at"):
                logger.warning(
                    f"recorded_at not provided for device {device_id}, mfr_device_id: {mfr_device_id}, using current time"
                )
                recorded_at = datetime.now(timezone.utc)
            else:
                recorded_at = device_data.get("recorded_at")

            # Get or create Source using the unique constraint fields (provider, manufacturer_id)
            # The unique constraint is on (das_tenant, provider, manufacturer_id), not on id.
            # If a Source with this manufacturer_id already exists, reuse it (even if device_id differs).
            # Pass id in defaults so it's only set when creating a new Source.
            if provider:
                source, created = models.Source.objects.get_or_create(
                    provider=provider, manufacturer_id=mfr_device_id, defaults={"id": device_id}
                )
            else:
                # Fallback: create source without provider reference
                source, created = models.Source.objects.get_or_create(
                    manufacturer_id=mfr_device_id, defaults={"id": device_id}
                )

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
                # Range queries are inclusive of the lower bound, exclusive of the upper bound, add a little padding to the upper bound
                # so this observation is included in the subject source's assigned range
                assigned_range_upper = (
                    recorded_at + timedelta(seconds=1) if recorded_at != datetime.max else recorded_at
                )
                assigned_range = DateTimeTZRange(lower=subject_source.assigned_range.lower, upper=assigned_range_upper)

            subject_source.location = device_location
            subject_source.assigned_range = assigned_range
            subject_source.save()

        # If all SubjectSource for the Subject are hauled, set Subject is_active to False
        # A SubjectSource is considered "hauled" if its assigned_range upper bound is not datetime.max
        # (i.e., the range has been closed). We check this instead of 'now not in assigned_range'
        # to avoid a race condition where 'now' might still be within the 1-second padding
        # added to the upper bound for recent haul events.
        max_upper = DEFAULT_ASSIGNED_RANGE[1]
        assigned_ranges = models.SubjectSource.objects.filter(subject=subject).values_list("assigned_range", flat=True)
        # Only consider hauled if there are SubjectSources AND all have a closed upper bound
        all_hauled = assigned_ranges.exists() and all(ar.upper != max_upper for ar in assigned_ranges)
        if all_hauled:
            subject.is_active = False
            subject.save()

        return subject, observations
