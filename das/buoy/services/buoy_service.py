from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from psycopg2.extras import DateTimeTZRange

from django.utils import timezone

from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from observations import models
from observations.models import DEFAULT_ASSIGNED_RANGE


class BuoyService:
    """Service encapsulating buoy/gear business logic used by views.

    Responsibilities:
    - create Subject if missing
    - create Observations for device events
    - create/update SubjectSource assigned ranges and locations
    - update Subject active state when all devices are hauled
    """

    @staticmethod
    def process_gearset(validated_data: dict, manufacturer: Optional[str] = None) -> List[models.Observation]:
        """Process a validated gearset payload.

        Args:
            validated_data (dict): validated serializer data for the gearset
            manufacturer (str|None): optional manufacturer string to store on the Subject.additional

        Returns:
            list: list of created Observation instances
        """
        set_id = validated_data.get("set_id")
        set_display_id = validated_data.get("set_display_id")
        devices = validated_data.get("devices", [])

        # Ensure subject subtype exists for buoy gear
        subject_subtype = None
        try:
            subject_subtype = models.SubjectSubType.objects.get(value=BUOY_GEAR_SUBJECT_SUBTYPE)
        except models.SubjectSubType.DoesNotExist:
            # If subtype not present, proceed without setting it (maintain backward compatibility)
            subject_subtype = None

        # Build additional dict for Subject defaults (include manufacturer if provided)
        additional = {}
        if set_display_id:
            additional["display_id"] = set_display_id
        if manufacturer:
            additional["manufacturer"] = manufacturer

        subject_defaults = {"additional": additional} if additional else {}

        # Create or get Subject for the gearset
        if subject_subtype is not None:
            subject, _ = models.Subject.objects.get_or_create(
                name=set_id, subject_subtype=subject_subtype, defaults=subject_defaults
            )
        else:
            subject, _ = models.Subject.objects.get_or_create(name=set_id, defaults=subject_defaults)

        # Ensure display_id and manufacturer are set/updated when provided
        if set_display_id or manufacturer:
            subj_additional = subject.additional or {}
            changed = False
            if set_display_id and subj_additional.get("display_id") != set_display_id:
                subj_additional["display_id"] = set_display_id
                changed = True
            if manufacturer and subj_additional.get("manufacturer") != manufacturer:
                subj_additional["manufacturer"] = manufacturer
                changed = True
            if changed:
                subject.additional = subj_additional
                subject.save()

        # Make a JSON-serializable copy of validated_data for storing in DB JSON fields
        def _make_serializable(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_make_serializable(v) for v in obj]
            return obj

        serializable_validated = _make_serializable(validated_data)

        observations = []

        # Store last_updated in Subject's additional field if provided
        if validated_data.get("last_updated"):
            subj_additional = subject.additional or {}
            subj_additional["last_updated"] = _make_serializable(validated_data["last_updated"])
            subject.additional = subj_additional
            subject.save()

        for device_data in devices:
            device_location = models.Point(device_data["location"]["longitude"], device_data["location"]["latitude"])
            recorded_at = device_data.get("recorded_at", timezone.now())

            source, _ = models.Source.objects.get_or_create(manufacturer_id=device_data["mfr_device_id"])

            # Store last_updated in Source's additional field if provided
            if device_data.get("last_updated"):
                source_additional = source.additional or {}
                source_additional["last_updated"] = _make_serializable(device_data["last_updated"])
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

            subject_source, _ = models.SubjectSource.objects.get_or_create(subject=subject, source=source)

            if device_data.get("device_status") == "deployed":
                assigned_range = DateTimeTZRange(lower=recorded_at, upper=DEFAULT_ASSIGNED_RANGE[1])
            else:
                # For haul events we expect subject_source to have a lower bound already set
                assigned_range = DateTimeTZRange(lower=subject_source.assigned_range.lower, upper=recorded_at)

            subject_source.location = device_location
            subject_source.assigned_range = assigned_range
            subject_source.save()

        # If all SubjectSource for the Subject are hauled, set Subject is_active to False
        all_hauled = all(ss.is_expired for ss in models.SubjectSource.objects.filter(subject=subject))
        if all_hauled:
            subject.is_active = False
            subject.save()

        return observations
