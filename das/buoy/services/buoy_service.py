from datetime import date, datetime
from decimal import Decimal

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
    def process_gearset(validated_data):
        """Process a validated gearset payload.

        Args:
            validated_data (dict): validated serializer data for the gearset

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

        subject_defaults = {"additional": {"display_id": set_display_id}} if set_display_id else {}

        # Create or get Subject for the gearset
        if subject_subtype is not None:
            subject, _ = models.Subject.objects.get_or_create(
                name=set_id, subject_subtype=subject_subtype, defaults=subject_defaults
            )
        else:
            subject, _ = models.Subject.objects.get_or_create(name=set_id, defaults=subject_defaults)

        # Ensure display_id is set when provided
        if set_display_id:
            additional = subject.additional or {}
            if additional.get("display_id") != set_display_id:
                additional["display_id"] = set_display_id
                subject.additional = additional
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

        for device_data in devices:
            device_location = models.Point(device_data["location"]["longitude"], device_data["location"]["latitude"])
            recorded_at = device_data.get("recorded_at", timezone.now())

            source, _ = models.Source.objects.get_or_create(manufacturer_id=device_data["mfr_device_id"])

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
