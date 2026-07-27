import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from psycopg2.extras import DateTimeTZRange

from django.db import IntegrityError, transaction

from buoy.constants import (
    BUOY_GEAR_SUBJECT_SUBTYPE,
    BUOY_GEAR_SUBJECT_SUBTYPE_DISPLAY,
    DEVICE_STATUS_DEPLOYED,
    DEVICE_STATUS_HAULED,
    GEAR_SUBJECT_TYPE,
    GEAR_SUBJECT_TYPE_DISPLAY,
)
from observations import models
from observations.models import DEFAULT_ASSIGNED_RANGE, EMPTY_POINT
from utils.json import ExtendedJSONEncoder

logger = logging.getLogger(__name__)

# Offset added to haul time for assigned_range upper bound.
# Range queries are inclusive of lower bound, exclusive of upper bound,
# so we add padding to ensure the haul observation is included in the range.
HAUL_TIME_OFFSET = timedelta(seconds=1)


class OlderGearsetRejectedError(ValueError):
    """Raised when posting an older gearset would conflict with a newer deployment of the same device(s)."""

    def __init__(self, message: str, device_id: str | None = None, newer_gearset_id=None):
        self.device_id = device_id
        self.newer_gearset_id = newer_gearset_id
        super().__init__(message)


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
    @transaction.atomic
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

        # Normalize recorded_at for each device once so the conflict-check pre-scan and the main
        # processing loop always use identical timestamps for the same device.
        # Use the status-appropriate payload timestamp when recorded_at is absent so conflict
        # decisions reflect the true event time rather than ingestion time.
        for device_data in devices:
            if not device_data.get("recorded_at"):
                device_status = device_data.get("device_status")
                if device_status == DEVICE_STATUS_DEPLOYED:
                    event_ts = device_data.get("last_deployed")
                elif device_status == DEVICE_STATUS_HAULED:
                    event_ts = device_data.get("last_updated")
                else:
                    event_ts = device_data.get("last_deployed") or device_data.get("last_updated")
                if event_ts is not None:
                    device_data["recorded_at"] = event_ts
                else:
                    logger.warning(
                        "recorded_at not provided for device %s (mfr_device_id: %s, status: %s), using current time",
                        device_data.get("device_id"),
                        device_data.get("mfr_device_id"),
                        device_status,
                    )
                    device_data["recorded_at"] = datetime.now(timezone.utc)

        # If a device is already deployed on another gearset, either reject (older payload) or close
        # that entire gearset and accept the new one. Reject if the payload's deployment time is
        # earlier than the existing deployment (older gearset posted); otherwise close previous and accept.
        max_upper = DEFAULT_ASSIGNED_RANGE[1]
        # Map subject_id -> haul_time for subjects we need to fully close
        subjects_to_close: dict = {}

        # Build a map of device_id -> recorded_at for deployed devices only
        deployed_device_recorded_at = {
            str(device_data["device_id"]): device_data["recorded_at"]
            for device_data in devices
            if device_data.get("device_status") == DEVICE_STATUS_DEPLOYED
        }

        if deployed_device_recorded_at:
            # Fetch all open deployments for the deployed devices in one query with row-level
            # locking to prevent concurrent requests from racing to close the same gearset.
            previous_deployments = (
                models.SubjectSource.objects.select_for_update()
                .filter(
                    source_id__in=deployed_device_recorded_at.keys(),
                    assigned_range__endswith=max_upper,
                )
                .exclude(subject_id=set_id)
                .select_related("subject")
            )
            for ss in previous_deployments:
                device_id = str(ss.source_id)
                recorded_at = deployed_device_recorded_at[device_id]
                # Reject if this is an older deployment (payload time before existing deployment start)
                existing_deploy_time = ss.assigned_range.lower
                if recorded_at <= existing_deploy_time:
                    raise OlderGearsetRejectedError(
                        f"Device {device_id} is already deployed on a newer gearset "
                        f"(set_id: {ss.subject_id}). Cannot post an older deployment "
                        f"(recorded_at={recorded_at} is not after existing deployment at {existing_deploy_time}).",
                        device_id=device_id,
                        newer_gearset_id=ss.subject_id,
                    )
                # Track the earliest recorded_at we see for this subject as the haul time
                if ss.subject_id in subjects_to_close:
                    subjects_to_close[ss.subject_id] = min(subjects_to_close[ss.subject_id], recorded_at)
                else:
                    subjects_to_close[ss.subject_id] = recorded_at

        for closed_subject_id, haul_time in sorted(subjects_to_close.items(), key=lambda kv: str(kv[0])):
            # Use exact haul_time (no offset) so the deployment Observation at recorded_at == haul_time
            # falls only in the new gearset's assigned_range; otherwise it would overlap both ranges.
            upper = haul_time
            # Close all deployed SubjectSources on this subject (entire gearset), with locking
            deployed_on_subject = list(
                models.SubjectSource.objects.select_for_update()
                .filter(
                    subject_id=closed_subject_id,
                    assigned_range__endswith=max_upper,
                )
                .select_related("source", "subject")
            )
            for ss in deployed_on_subject:
                if upper <= ss.assigned_range.lower:
                    # An empty range (upper <= lower) would be canonicalized by PostgreSQL and
                    # later re-opened by SubjectSource.save(). Treat this as a conflict.
                    device_identifier = getattr(ss.source, "manufacturer_id", str(ss.source_id))
                    raise OlderGearsetRejectedError(
                        f"Device {device_identifier} is already deployed on a newer gearset "
                        f"(set_id: {closed_subject_id}). Cannot close previous deployment: "
                        f"haul_time {upper} is not after existing deployment start "
                        f"{ss.assigned_range.lower}.",
                        device_id=str(ss.source_id),
                        newer_gearset_id=closed_subject_id,
                    )
                ss.assigned_range = DateTimeTZRange(lower=ss.assigned_range.lower, upper=upper)
                logger.debug(
                    "Closing previous deployment of device %s from gearset %s (set_id: %s) at %s",
                    getattr(ss.source, "manufacturer_id", ss.source_id),
                    ss.subject.name,
                    closed_subject_id,
                    upper,
                )
            if deployed_on_subject:
                models.SubjectSource.objects.bulk_update(deployed_on_subject, ["assigned_range"])
            closed_subject = models.Subject.objects.get(id=closed_subject_id)
            closed_subject.is_active = False
            closed_subject.save()
            logger.info(
                "Closed %d deployed device(s) for gearset %s (set_id: %s) at haul_time=%s",
                len(deployed_on_subject),
                closed_subject.name,
                closed_subject_id,
                upper,
            )

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
        gear_subject_type, _ = models.SubjectType.objects.get_or_create(
            value=GEAR_SUBJECT_TYPE, defaults={"display": GEAR_SUBJECT_TYPE_DISPLAY}
        )
        subject_subtype, _ = models.SubjectSubType.objects.get_or_create(
            value=BUOY_GEAR_SUBJECT_SUBTYPE,
            defaults={"display": BUOY_GEAR_SUBJECT_SUBTYPE_DISPLAY, "subject_type": gear_subject_type},
        )

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
        subject, created = models.Subject.objects.get_or_create(
            id=set_id, subject_subtype=subject_subtype, defaults=subject_defaults
        )

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

            recorded_at = device_data["recorded_at"]

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
                new_last_updated = BuoyService._make_serializable(device_data["last_updated"])
                source_additional = source.additional or {}
                if source_additional.get("last_updated") != new_last_updated:
                    source_additional["last_updated"] = new_last_updated
                    source.additional = source_additional
                    source.save()

            # Store the validated payload as the raw field for traceability.
            # Use update_or_create so that re-submitting the same device at the same
            # recorded_at (e.g. when a device is added to an existing gearset and the
            # full set is re-sent) is idempotent instead of hitting the unique constraint
            # on (das_tenant_id, source_id, recorded_at).
            observation, _obs_created = models.Observation.objects.update_or_create(
                source=source,
                recorded_at=recorded_at,
                defaults={
                    "location": device_location,
                    "additional": {"raw": serializable_validated},
                },
            )
            observations.append(observation)

            subject_source, subject_source_created = models.SubjectSource.objects.get_or_create(
                subject=subject, source=source
            )

            if device_data.get("device_status") == DEVICE_STATUS_DEPLOYED:
                assigned_range = DateTimeTZRange(lower=recorded_at, upper=DEFAULT_ASSIGNED_RANGE[1])
            else:
                assigned_range_upper = recorded_at + HAUL_TIME_OFFSET if recorded_at != datetime.max else recorded_at
                if subject_source_created:
                    # New device appearing for the first time in a haul payload (e.g. added to an
                    # existing trawl). Use last_deployed as the lower bound so the deployment window
                    # is meaningful; fall back to recorded_at if last_deployed is missing.
                    assigned_range_lower = device_data.get("last_deployed") or recorded_at
                    logger.info(
                        f"SubjectSource created during haul for {subject.name} and {source.manufacturer_id}; "
                        f"using last_deployed={assigned_range_lower} as assigned_range lower bound"
                    )
                else:
                    assigned_range_lower = subject_source.assigned_range.lower
                assigned_range = DateTimeTZRange(lower=assigned_range_lower, upper=assigned_range_upper)

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

        # Sync Subject.is_active with the SubjectSource assigned ranges.
        # A SubjectSource is considered "hauled" if its assigned_range upper bound is not datetime.max
        # (i.e., the range has been closed). We check this instead of 'now not in assigned_range'
        # to avoid a race condition where 'now' might still be within the 1-second padding
        # added to the upper bound for recent haul events.
        assigned_ranges = list(
            models.SubjectSource.objects.filter(subject=subject).values_list("assigned_range", flat=True)
        )
        # Only consider hauled if there are SubjectSources AND all have a closed upper bound
        all_hauled = bool(assigned_ranges) and all(ar.upper != max_upper for ar in assigned_ranges)
        has_open_deployment = any(ar.upper == max_upper for ar in assigned_ranges)
        if all_hauled:
            subject.is_active = False
            subject.save()
        elif has_open_deployment and not subject.is_active:
            # Redeploy of a previously hauled gearset under the same set_id (e.g. RMW Hub
            # reuses the set_id when a set was accidentally marked hauled). Reactivate so
            # the set's status matches its open deployment.
            subject.is_active = True
            subject.save()
            logger.info(
                "Reactivated gearset %s (set_id: %s): deploy received for previously hauled subject",
                subject.name,
                subject.id,
            )

        return subject, observations
