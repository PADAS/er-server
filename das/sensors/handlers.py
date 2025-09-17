import logging
from datetime import datetime, timezone
from typing import Literal, Optional, Union

import pytz
from dateutil.parser import parse as parse_date
from psycopg2.errors import UniqueViolation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import IntegrityError
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from analyzers import gfw_inbound
from buoy.constants import BUOY_SUBJECT_SUBTYPE, TRAP_DEPLOYED, TRAP_RETRIEVED
from observations import servicesutils
from observations.models import (
    DEFAULT_ASSIGNED_RANGE,
    DateTimeTZRange,
    Observation,
    Source,
    Subject,
    SubjectSource,
    update_subject_status_from_post,
)
from observations.serializers import ObservationSerializer
from sensors.serializers import SensorPostParameters
from sensors.subject_name_change import HandlerERTrack
from sensors.vehicle_tracker import (
    DasObservation,
    EzyTrackAdapter,
    EzytrackObservation,
    FollowltObservation,
    SkylineAdapter,
    SkylineObservations,
    TractAdapter,
    TractVehicleData,
)
from tracking.pubsub_registry import notify_new_tracks
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)

User = get_user_model()

# Type alias for trap event types
TrapEventType = Union[Literal["trap_deployed"], Literal["trap_retrieved"]]


class GenericSensorHandler:
    SENSOR_TYPE = "generic"
    DEFAULT_SOURCE_TYPE = "gps-radio"
    DEFAULT_SUBJECT_SUBTYPE = "ranger"
    DEFAULT_EVENT_ACTION = None
    serializer_class = SensorPostParameters

    @classmethod
    def handle_heartbeat(cls, data: dict, provider_key: str):
        servicesutils.store_service_status(provider_key=provider_key, data=data)

        extradata = {"data": {"provider_key": provider_key, **data}}
        logger.info("DRA heartbeat", extra=extradata)

        return Response(data, status=status.HTTP_200_OK)

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        data = request.data
        if isinstance(data, dict):
            # Default to 'observation' for backward compatibility.
            key = data.get("message_key", "observation")

            if key == "heartbeat":
                return cls.handle_heartbeat(data, provider_key)

        observations_json = data
        if isinstance(observations_json, dict):
            observations_json = [observations_json]

        params = SensorPostParameters(data=observations_json, many=True)
        if not params.is_valid():
            return Response(data=params.errors, status=status.HTTP_400_BAD_REQUEST)

        return cls.process_all_observations(params.validated_data, provider_key, sensor_type, request.user)

    @classmethod
    def generate_batches(cls, observations, batch_size):
        num_observations = len(observations)
        for start_index in range(0, num_observations, batch_size):
            yield observations[start_index : min(start_index + batch_size, num_observations)]

    @classmethod
    def save_and_notify_tracks_listeners(cls, obs_to_persist, errors, obs_cache):
        # save and notify only if there are new, non-dup observations

        error_status = status.HTTP_400_BAD_REQUEST

        def notify_tracks_listeners():
            src_ids = {src_id for (src_id, _) in obs_cache}
            for src_id in src_ids:
                notify_new_tracks(src_id)

        if obs_to_persist:
            bulk_serializer = ObservationSerializer(data=obs_to_persist, many=True)
            if bulk_serializer.is_valid():
                try:
                    bulk_serializer.save()
                except IntegrityError as e:
                    logger.error("Error saving observations: %s", e)
                    error_status = status.HTTP_409_CONFLICT
                    errors.append(str(e))
            else:
                errors.append(bulk_serializer.errors)
            transaction.on_commit(notify_tracks_listeners)
        for error in errors:
            if error:
                return Response(errors, status=error_status)

    @classmethod
    def process_all_observations(cls, data: list, provider_key: str, sensor_type: str, user, batch_size: int = 128):
        logger.info("Processing %s observations", len(data), extra={"observation_count": len(data)})

        # Sort observations by recorded_at in ascending order
        sorted_data = sorted(data, key=lambda x: x.get("recorded_at"))

        try:
            try:
                return cls.process_observations(
                    data=sorted_data,
                    provider_key=provider_key,
                    sensor_type=sensor_type,
                    user=user,
                    batch_size=batch_size,
                )
            except UniqueViolation:
                return cls.process_observations(
                    data=sorted_data,
                    provider_key=provider_key,
                    sensor_type=sensor_type,
                    user=user,
                    batch_size=batch_size,
                )
        except UniqueViolation:
            return Response({}, status=status.HTTP_409_CONFLICT)

    @classmethod
    def process_observations(cls, data: list, provider_key: str, sensor_type: str, user: User, batch_size: int):
        created = False
        obs_to_persist, errors, obs_cache = [], [], set()
        source_cache = {}  # Cache for sources to avoid redundant ensure_source calls
        batches = cls.generate_batches(data, batch_size)
        for batch in batches:
            for an_observation in batch:
                created |= cls.process_one_observation(
                    an_observation=an_observation,
                    provider_key=provider_key,
                    sensor_type=sensor_type,
                    obs_to_persist=obs_to_persist,
                    obs_cache=obs_cache,
                    errors=errors,
                    user=user,
                    source_cache=source_cache,
                )
        if response := cls.save_and_notify_tracks_listeners(obs_to_persist, errors, obs_cache):
            return response

        return Response({}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @classmethod
    def find_subject_by_name(cls, name: str):
        """Find a subject by its name."""
        try:
            return Subject.objects.get(name=name)
        except Subject.DoesNotExist:
            return None
        except Subject.MultipleObjectsReturned:
            # Get all subjects with the same name, ordered by creation date
            subjects = Subject.objects.filter(name=name).order_by("created_at")
            first_subject = subjects.first()
            duplicate_subjects = subjects.exclude(id=first_subject.id)

            # Transfer SubjectSource assignments from duplicates to the first subject
            cls._transfer_subject_source_assignments(first_subject, duplicate_subjects)

            return first_subject

    @classmethod
    def _transfer_subject_source_assignments(cls, target_subject: Subject, duplicate_subjects):
        """Transfer SubjectSource assignments from duplicate subjects to the target subject.

        Args:
            target_subject (Subject): The subject to receive the assignments
            duplicate_subjects (QuerySet): The duplicate subjects to transfer assignments from
        """
        from django.db import transaction

        with transaction.atomic():
            for duplicate_subject in duplicate_subjects:
                # Get all SubjectSource assignments for the duplicate subject
                assignments = SubjectSource.objects.filter(subject=duplicate_subject)
                for assignment in assignments:
                    # Check if target subject already has an assignment with the same source and overlapping range
                    existing_assignment = SubjectSource.objects.filter(
                        subject=target_subject,
                        source=assignment.source,
                        assigned_range__overlap=assignment.assigned_range,
                    ).first()

                    if existing_assignment:
                        if assignment.assigned_range.lower < existing_assignment.assigned_range.lower:
                            from observations.models import DateTimeTZRange

                            existing_assignment.assigned_range = DateTimeTZRange(
                                lower=assignment.assigned_range.lower,
                                upper=max(assignment.assigned_range.upper, existing_assignment.assigned_range.upper),
                            )
                            existing_assignment.save()
                        assignment.delete()
                    else:
                        assignment.subject = target_subject
                        assignment.save()
                    duplicate_subject.delete()

    @classmethod
    def update_subject(cls, subject: Subject, additional: Optional[dict] = None, is_active: Optional[bool] = None):
        """Update a subject with additional fields."""
        updated_fields = set()
        if additional:
            subject.additional = additional
            updated_fields.add("additional")
        if is_active is not None:
            subject.is_active = is_active
            updated_fields.add("is_active")
        if updated_fields:
            updated_fields.add("updated_at")
        subject.save(update_fields=updated_fields)
        return subject

    @classmethod
    def update_subject_source_assigned_range(
        cls,
        subject_source: SubjectSource,
        recorded_at: datetime,
        event_type: TrapEventType,
    ):
        """Update the assigned range of a subject source."""
        trap_id = subject_source.source.manufacturer_id
        if event_type == TRAP_DEPLOYED:
            if subject_source.has_assigned_range and subject_source.is_current:
                raise ValidationError(f"Cannot deploy a trap ({trap_id}) that is already deployed.")
            subject_source.assigned_range = DateTimeTZRange(lower=recorded_at, upper=DEFAULT_ASSIGNED_RANGE[1])
        else:
            if not subject_source.has_assigned_lower_range:
                raise ValidationError(f"Cannot retrieve a trap ({trap_id}) that is not deployed.")
            if subject_source.has_assigned_upper_range:
                raise ValidationError(f"Cannot retrieve a trap ({trap_id}) that is already retrieved.")
            current_lower = subject_source.assigned_range.lower
            subject_source.assigned_range = DateTimeTZRange(lower=current_lower, upper=recorded_at)

        subject_source.save()

    @classmethod
    def process_one_observation(
        cls,
        an_observation: dict,
        provider_key: str,
        sensor_type: str,
        obs_to_persist: list,
        obs_cache: set,
        errors: list,
        user: User,
        source_cache: dict = None,
    ):
        """return True if an observation was created

        Args:
            an_observation (dict): observation to process
            provider_key (str): provider key
            sensor_type (str): sensor type
            obs_to_persist (list): list of observations to save to the database
            obs_cache (set): set of observation keys, so if there is a duplicate on source_id+recorded_at, we don't process it again
            errors (list): list of errors
            user (User): user who is processing the observation
            source_cache (dict, optional): Cache of sources to avoid redundant ensure_source calls. Defaults to None.
        """
        manufacturer_id = an_observation["manufacturer_id"]
        location = an_observation["location"]
        lat = location.get("lat", None)
        lon = location.get("lon", None)
        now = datetime.now(timezone.utc)
        # location = Point(x=float(lon), y=float(lat))
        location = {"latitude": float(lat), "longitude": float(lon)}
        subject_subtype = an_observation.get("subject_subtype") or cls.DEFAULT_SUBJECT_SUBTYPE
        source_type = an_observation.get("source_type", provider_key)
        model_name = an_observation.get("model_name", None) or "{}:{}".format(sensor_type, provider_key)
        subject_name = an_observation.get("subject_name") or manufacturer_id
        subject_additional = an_observation.get("subject_additional", None)
        recorded_at = an_observation.get("recorded_at")

        subject_info = {
            "subject_subtype_id": subject_subtype,
            "name": subject_name,
            "subject_groups": clean_subjectgroups(an_observation.get("subject_groups")),
            "id": an_observation.get("subject_id"),
        }
        if subject_additional is not None:
            subject_info["additional"] = subject_additional

        source_info = {}
        if an_observation.get("source_additional") is not None:
            source_info["additional"] = an_observation["source_additional"]

        observation_additional = an_observation.get("additional", {})

        # Special initial validation for ropeless_buoy_gearset
        if subject_subtype == BUOY_SUBJECT_SUBTYPE:
            event_type = observation_additional.get("event_type")
            if event_type not in [TRAP_DEPLOYED, TRAP_RETRIEVED]:
                raise ValidationError(
                    f"Ropeless buoy gearset observations must have an additional.event_type of "
                    f"'{TRAP_DEPLOYED}' or '{TRAP_RETRIEVED}'."
                )
            subject_info.setdefault("additional", {})["display_id"] = subject_name
            subject = cls.find_subject_by_name(subject_name)
            if subject:
                subject_info["id"] = subject.id

        # Create a cache key from the source parameters
        source_cache_key = (source_type, provider_key, manufacturer_id, model_name, str(subject_info), str(source_info))

        # Use cached source if available
        if source_cache is not None and source_cache_key in source_cache:
            src = source_cache[source_cache_key]
        else:
            src = Source.objects.ensure_source(
                source_type,
                provider=provider_key,
                manufacturer_id=manufacturer_id,
                model_name=model_name,
                subject=subject_info,
                **source_info,
            )
            if source_cache is not None:
                source_cache[source_cache_key] = src

        if subject_subtype == BUOY_SUBJECT_SUBTYPE:
            subject = cls.find_subject_by_name(subject_name)
            if not subject:
                subject = Subject.objects.create_subject(**subject_info)

            subject_source, created = SubjectSource.objects.get_or_create(
                source=src, subject=subject, defaults={"assigned_range": DEFAULT_ASSIGNED_RANGE}
            )

            cls.update_subject_source_assigned_range(
                subject_source=subject_source,
                recorded_at=recorded_at,
                event_type=observation_additional.get("event_type"),
            )

            has_active_sources = subject.subjectsources.filter(assigned_range__contains=now).exists()
            cls.update_subject(subject, additional=subject_additional, is_active=has_active_sources)

        event_action = an_observation.get("additional", {}).get("event_action", cls.DEFAULT_EVENT_ACTION)
        observation = {
            "location": location,
            "recorded_at": recorded_at,
            "source": str(src.id),
            "additional": observation_additional,
        }

        # Get the subject for exclusion checks
        subject = src.assigned_subject if hasattr(src, "assigned_subject") else None

        observation = cls.apply_exclusion_flags(observation, an_observation, location, observation_additional, subject)

        obs_key = (str(src.id), recorded_at)
        # Short-circuit if we already have this observation.
        if obs_key in obs_cache:
            return False

        try:
            existing_observation = Observation.objects.get(source=src, recorded_at=recorded_at)
            logger.debug("Processed duplicate observation %s", subject_subtype, extra={"obs.dup": provider_key})
            errors.append({})
            if event_action:
                logger.info(
                    "Processing new radio status",
                    extra={"radio.status.update": provider_key, "radio.event_action": event_action},
                )

                update_subject_status_from_post(
                    existing_observation.source,
                    recorded_at=recorded_at,
                    location=location,
                    additional={"subject_name": subject_name, **observation_additional},
                )

            return False
        except Observation.DoesNotExist:
            pass

        created = False
        obs_cache.add(obs_key)
        # TODO: constructing serializers in 2 different places - this below
        # validates each observation
        validator = ObservationSerializer(data=observation)
        if validator.is_valid():
            obs_to_persist.append(observation)
            logger.debug("Added new observation %s", observation, extra={"obs.new": provider_key})
            errors.append({})
            created = True
        else:
            errors.append(validator.errors)

        return created

    @classmethod
    def apply_exclusion_flags(
        cls,
        observation_dict: dict,
        an_observation: dict,
        location: Optional[dict] = None,
        additional: Optional[dict] = None,
        subject: Optional[object] = None,
    ):
        """Apply exclusion flags to an observation dictionary.

        This method handles both manual exclusion flags from the observation data
        and automatic exclusion flags based on location/accuracy conditions.

        Args:
            observation_dict (dict): The observation dictionary to modify
            an_observation (dict): The raw observation data from the sensor
            location (dict, optional): Location data for automatic exclusion checks
            additional (dict, optional): Additional data for automatic exclusion checks
            subject (object, optional): Subject object for exclusion checks

        Returns:
            dict: The modified observation dictionary with exclusion flags applied
        """
        # Handle manual exclusion flags from observation data
        if (exclusion_flags := an_observation.get("exclusion_flags", 0)) != 0:
            observation_dict["exclusion_flags"] = observation_dict.get("exclusion_flags", 0) | exclusion_flags

        # Handle automatic exclusion flags based on conditions
        if cls.should_exclude_automatically(
            location=location, additional=additional, subject=subject, recorded_at=an_observation.get("recorded_at")
        ):
            observation_dict["exclusion_flags"] = (
                observation_dict.get("exclusion_flags", 0) | Observation.EXCLUDED_AUTOMATICALLY
            )

        return observation_dict

    @classmethod
    def should_exclude_automatically(
        cls, location: dict, additional: dict, subject: Optional[Subject] = None, recorded_at: Optional[str] = None
    ) -> bool:
        """Determine if an observation should be automatically excluded.

        This method can be overridden by subclasses to implement custom
        exclusion logic based on location, additional data, and subject information.

        Args:
            location (dict): Location data containing latitude and longitude
            additional (dict): Additional observation data
            subject (Subject, optional): Subject object for exclusion checks
            recorded_at (str, optional): Recorded timestamp for future time checks

        Returns:
            bool: True if the observation should be automatically excluded
        """
        # Check for future timestamps
        if recorded_at:
            try:
                # Parse the recorded_at timestamp
                if isinstance(recorded_at, str):
                    parsed_time = parse_date(recorded_at)
                else:
                    parsed_time = recorded_at

                # Ensure timezone awareness
                if not parsed_time.tzinfo:
                    parsed_time = pytz.utc.localize(parsed_time)

                # Check if the timestamp is in the future
                current_offset_time = datetime.now(timezone.utc) + Observation.EXCLUDED_AUTOMATICALLY_TIME_DELTA
                if parsed_time > current_offset_time:
                    return True
            except (ValueError, TypeError):
                # If we can't parse the timestamp, don't exclude based on time
                pass
        if location:
            # Check for invalid coordinates (0,0) or (1,1) for non-stationary subjects
            lat, lon = int(location.get("latitude", 0)), int(location.get("longitude", 0))
            if (lat, lon) == (0, 0) or (lat, lon) == (1, 1):
                return not subject or not subject.is_stationary_subject

        return False


class ErTrackHandler(GenericSensorHandler):
    SENSOR_TYPE = "ertrack"
    DEFAULT_SUBJECT_SUBTYPE = "er_mobile"
    OVERRIDE_SUBJECT_SUBTYPE = "ranger"

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        observations_json = request.data
        if isinstance(observations_json, dict):
            observations_json = [observations_json]

        observations_json = cls.clean_invalid_ermobile_observations(observations_json)
        if isinstance(observations_json, Response):
            return observations_json

        params = SensorPostParameters(data=observations_json, many=True)
        if not params.is_valid():
            return Response(data=params.errors, status=status.HTTP_400_BAD_REQUEST)
        return cls.process_all_observations(params.validated_data, provider_key, sensor_type, request.user)

    @classmethod
    def ensure_source(cls, observation, user, subject_info, **kwargs):
        with transaction.atomic():
            source, source_created = Source.objects.get_source(**kwargs)
            if source_created and not subject_info:
                subject_model = Subject.objects.create_subject(**{"name": source.manufacturer_id})
                SubjectSource.objects.create(source=source, subject=subject_model)
            elif subject_info:
                recorded_at = observation.get("recorded_at")
                handler_er_track = HandlerERTrack(
                    source=source,
                    is_new_source=source_created,
                    subject_name=subject_info.get("name"),
                    subject_subtype_id=subject_info.get("subject_subtype_id"),
                    recorded_at=recorded_at,
                    user=user,
                    observation=observation,
                )
                handler_er_track.handle()
            return source

    @classmethod
    def process_one_observation(
        cls,
        an_observation: dict,
        provider_key: str,
        sensor_type: str,
        obs_to_persist: list,
        obs_cache: set,
        errors: list,
        user: User,
        source_cache: dict = None,
    ):
        manufacturer_id = an_observation["manufacturer_id"]
        location = an_observation["location"]
        lat = location.get("lat", None)
        lon = location.get("lon", None)
        location = {"latitude": float(lat), "longitude": float(lon)}
        subject_subtype = an_observation.get("subject_subtype") or cls.DEFAULT_SUBJECT_SUBTYPE
        if subject_subtype == cls.OVERRIDE_SUBJECT_SUBTYPE:
            subject_subtype = cls.DEFAULT_SUBJECT_SUBTYPE
        source_type = an_observation.get("source_type", provider_key) or provider_key
        model_name = an_observation.get("model_name", None) or "{}:{}".format(sensor_type, provider_key)
        subject_name = an_observation.get("subject_name") or manufacturer_id
        subject_info = {
            "subject_subtype_id": subject_subtype,
            "name": subject_name,
            "subject_groups": clean_subjectgroups(an_observation.get("subject_groups")),
            "id": an_observation.get("subject_id"),
        }
        if an_observation.get("subject_additional") is not None:
            subject_info["additional"] = an_observation["subject_additional"]

        source_info = {}
        if an_observation.get("source_additional") is not None:
            source_info["additional"] = an_observation["source_additional"]
        er_mobile_info = {k: v for k, v in an_observation.items() if k in ["subject_id", "user_id"]}

        # Create a cache key from the source parameters
        # A single ER Mobile could be sending observations for more than one subject,
        # on the same source. If the subject changes, we need to redo by calling
        # ensure_source which sets up the subject and subjectsource with a new date range.
        source_cache_key = (
            source_type,
            provider_key,
            manufacturer_id,
            model_name,
            str(subject_info),
            str(source_info),
            str(er_mobile_info),
        )

        # Use cached source if available
        if source_cache is not None and source_cache_key in source_cache:
            src = source_cache[source_cache_key]
        else:
            src = cls.ensure_source(
                observation=an_observation,
                user=user,
                subject_info=subject_info,
                source_type=source_type,
                provider=provider_key,
                manufacturer_id=manufacturer_id,
                model_name=model_name,
                **source_info,
            )
            if source_cache is not None:
                source_cache.clear()
                source_cache[source_cache_key] = src

        recorded_at = an_observation.get("recorded_at")
        additional = an_observation.get("additional", {})
        observation = {
            "location": location,
            "recorded_at": recorded_at,
            "source": str(src.id),
            "additional": additional,
        }

        # Get the subject for exclusion checks
        subject = src.assigned_subject if hasattr(src, "assigned_subject") else None

        observation = cls.apply_exclusion_flags(observation, an_observation, location, additional, subject)

        obs_key = (str(src.id), recorded_at)
        # Short-circuit if we already have this observation.
        if obs_key in obs_cache or Observation.objects.filter(source=src, recorded_at=recorded_at).exists():
            logger.debug("Processed duplicate observation %s", subject_subtype, extra={"obs.dup": provider_key})
            errors.append({})
            return False

        created = False
        obs_cache.add(obs_key)
        validator = ObservationSerializer(data=observation)
        if validator.is_valid():
            obs_to_persist.append(observation)
            logger.debug("Added new observation %s", observation, extra={"obs.new": provider_key})
            errors.append({})
            created = True
        else:
            errors.append(validator.errors)
        return created

    @classmethod
    def clean_invalid_ermobile_observations(cls, observations):
        """See ERA-9406, return 200 for ER Mobile when their observation library sends an invalid payload

        Args:
            observations (list): raw observations from the request

        Returns:
            [list, Response): cleaned observations, or the Response to return
        """
        compliant_observations = []
        for observation in observations:
            if observation.get("event") or observation.get("coords"):
                logger.warning("Invalid ER Mobile observation received: %s", observation)
                continue
            compliant_observations.append(observation)
        if not compliant_observations:
            return Response(data={"message": "Invalid ER Mobile observations received"}, status=status.HTTP_200_OK)
        return compliant_observations

    @classmethod
    def should_exclude_automatically(
        cls, location: dict, additional: dict, subject: Optional[object] = None, recorded_at: Optional[str] = None
    ) -> bool:
        threshold = int(
            get_tenant_settings().env_settings.observation_accuracy_threshold or settings.OBSERVATION_ACCURACY_THRESHOLD
        )

        # Check for high accuracy (existing logic)
        if additional and int(additional.get("accuracy", 0)) >= threshold:
            return True

        # Call parent class method for other checks (future time, invalid coordinates)
        return super().should_exclude_automatically(
            location=location, additional=additional, subject=subject, recorded_at=recorded_at
        )


class FollowltTrackerHandler:
    SENSOR_TYPE = "animal-collar-push"
    DEFAULT_SOURCE_TYPE = "tracking-device"
    MODEL_NAME = "FollowIt"
    serializer_class = FollowltObservation

    @staticmethod
    def convert_to_das_format(data):
        location = {"latitude": data.get("lat"), "longitude": data.get("lng")}
        try:
            recorded_at = parse_date(data.get("date"))
            if not recorded_at.tzinfo:
                recorded_at = pytz.utc.localize(recorded_at)
        except Exception as e:
            logger.error(e)
            raise e
        additional = dict()
        for key in data.keys():
            if key not in ["lat", "lng", "date"] and data.get(key, None):
                additional[key] = data.get(key, None)
        return dict(location=location, recorded_at=recorded_at, additional=additional)

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE
        logger.info("Recieved new push message from {}: {}".format(sensor_type, request.data))
        sensor_observations = request.data
        # Check if received data is in list format or not
        if isinstance(sensor_observations, dict):
            sensor_observations = [sensor_observations]
        errors = []
        for sensor_observation in sensor_observations:
            # Serialize sensor api data (one at a time), So that if there are
            # some errors, let's not discard whole payload and throw error
            params = FollowltObservation(data=sensor_observation)
            if not params.is_valid():
                errors.append(params.errors)
                continue
            try:
                data = cls.convert_to_das_format(params.data)
                model_name = "{}:{}".format(cls.MODEL_NAME, provider_key)
                source_type = cls.DEFAULT_SOURCE_TYPE
                manufacturer_id = params.data.get("collarId")
                source_additional = dict(serialId=params.data.get("serialId"), name=params.data.get("name"))
                src = Source.objects.ensure_source(
                    source_type=source_type,
                    provider=provider_key,
                    manufacturer_id=manufacturer_id,
                    model_name=model_name,
                    additional=source_additional,
                )
                # Short-circuit if we already have this observation.
                if Observation.objects.filter(source=src, recorded_at=data["recorded_at"]).exists():
                    logger.info("Processed duplicate " "observation: {}".format(data))
                    errors.append({})
                    continue
                data["source"] = str(src.id)
                serializer = ObservationSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                    logger.info("Added new observation %s", data)
                    notify_new_tracks(src.id)
                    errors.append({})
                else:
                    errors.append(serializer.errors())
            except Exception as e:
                logger.error(str(e))
                errors.append(str(e))
        for error in errors:
            if error:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({}, status=status.HTTP_201_CREATED)


class LocationDictSerializer(serializers.Serializer):
    lon = serializers.FloatField(min_value=-180.0, max_value=180.0)
    lat = serializers.FloatField(min_value=-90.0, max_value=90.0)


class RadioAdditionalSerializer(serializers.Serializer):
    event_action = serializers.CharField(max_length=40)
    radio_state = serializers.CharField(max_length=20)
    radio_state_at = serializers.DateTimeField()
    last_voice_call_start_at = serializers.DateTimeField(required=False)
    location_requested_at = serializers.DateTimeField(required=False)


def clean_subjectgroups(subjectgroups):
    if subjectgroups:
        subjectgroups = [sg for sg in subjectgroups if sg]
    return subjectgroups


class DasRadioAgentHandler(GenericSensorHandler):
    """
    Deprecated. I need to move das-radio-agent to the generic handler above.
    """

    SENSOR_TYPE = "dasradioagent"
    DEFAULT_SOURCE_TYPE = SOURCE_TYPE = "gps-radio"
    DEFAULT_SUBJECT_SUBTYPE = "ranger"
    DEFAULT_EVENT_ACTION = "unknown"


class GsatHandler:
    SENSOR_TYPE = "gsat"
    SOURCE_TYPE = "gps-radio"
    DEFAULT_SUBJECT_SUBTYPE = "ranger"

    @staticmethod
    def _parse_location(lat, lon):
        try:
            # return Point(x=float(lon), y=float(lat))
            return {"latitude": float(lat), "longitude": float(lon)}
        except:
            raise

    @staticmethod
    def _parse_gsat_request(o):
        r = {}
        r["manufacturer_id"] = str(o.get("uniqueid"))
        r["location"] = GsatHandler._parse_location(o.get("lat"), o.get("lng"))
        r["recorded_at"] = GsatHandler._parse_gsat_timestamp(o)

        try:
            r["altitude_meters"] = float(o.get("alt"))
        except:
            pass

        try:
            r["speed_mps"] = float(o.get("speed"))
        except:
            pass

        try:
            r["heading"] = float(o.get("head"))
        except:
            pass

        # Calculate state, that will be recorded in SubjectStatus.
        r["state"] = "alarm" if o.get("emer", 0) == "1" else "default"

        r["events"] = o.get("events").split(",") if len(o.get("events", "")) > 0 else None

        r["sensor_type"] = GsatHandler.SENSOR_TYPE

        return r

    @staticmethod
    def _parse_gsat_timestamp(obj):
        try:
            return datetime.fromtimestamp(int(obj.get("time")), tz=pytz.UTC)
        except:
            return datetime.now(tz=pytz.UTC)

    REQUIRED_PARAMS = (
        "uniqueid",
        "lat",
        "lng",
        "time",
    )
    OPTIONAL_PARAMS = (
        "alt",
        "head",
        "speed",
        "emer",
    )

    @staticmethod
    def _validate_template_request(qp):
        template = {
            "uniqueid": "{uniqueid}",
            "lat": "{lat}",
            "lng": "{lng}",
            "time": "{time}",
            "alt": "{altitude}",
            "head": "{heading}",
            "speed": "{speed}",
            "emer": "{isemergency}",
        }

        if all(qp[k] == template[k] for k in qp if k in template) and all(_ in qp for _ in GsatHandler.REQUIRED_PARAMS):
            return True

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info("Gsat request: %s", request.query_params)

        try:
            obj = GsatHandler._parse_gsat_request(request.query_params)
        # except ValueError as ve:
        except Exception:
            if cls._validate_template_request(request.query_params):
                return Response({"data": "That looks like a valid template request"})
            else:
                return Response({"data": "Check query parameters and try again."}, status=status.HTTP_400_BAD_REQUEST)

        obj["provider_key"] = provider_key

        model_name = "{}:{}".format(GsatHandler.SENSOR_TYPE, provider_key)

        src, created = Source.objects.ensure_source(
            cls.SOURCE_TYPE, provider=provider_key, manufacturer_id=obj.get("manufacturer_id"), model_name=model_name
        )

        # If the Source already exists, assume the SubjectSource and Subject
        # already exist.
        if created:
            ss, created = SubjectSource.objects.ensure_subject_source(
                src, timestamp=obj["recorded_at"], subject_subtype_id=cls.DEFAULT_SUBJECT_SUBTYPE
            )

        obj["additional"] = dict(
            (k, obj[k])
            for k in obj
            if k
            not in (
                "manufacturer_id",
                "location",
                "recorded_at",
            )
        )
        obj["source"] = str(src.id)

        serializer = ObservationSerializer(data=obj)
        if serializer.is_valid():
            serializer.save()

            notify_new_tracks(src.id)
            logger.info(
                "Processed duplicate %s observation", cls.DEFAULT_SUBJECT_SUBTYPE, extra={"obs.new": provider_key}
            )
            # GSAT service expects 200 and considers anything else bad.
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SkylineVehicleTrackerHandler:
    SENSOR_TYPE = "vehicle-tracker-push"
    DEFAULT_SUBJECT_SUBTYPE = "truck"
    serializer_class = SkylineObservations

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info("Recieved new push message %s", request.data, extra={"msg.data": request.data})
        params = SkylineObservations(data=request.data)

        # short term don't throw away bad data, until
        # we understand what skyline is sending us
        if not params.is_valid():
            status_fail = {"status": 105, "message": params.errors}
            return Response(data=status_fail, status=status.HTTP_400_BAD_REQUEST)

        adapter = SkylineAdapter()
        # TODO bulk_create
        # obs_to_insert = []

        for observation in params.data["Messages"]:
            das_obs = adapter.create_das_object(observation)

            src = Source.objects.ensure_source(
                das_obs.source_type,
                provider=provider_key,
                manufacturer_id=das_obs.manufacturer_id,
                model_name=das_obs.model_name,
                subject={"subject_subtype_id": das_obs.subject_subtype, "name": das_obs.subject_name},
            )
            # skip if we already have this observation.
            if Observation.objects.filter(source=src, recorded_at=das_obs.recorded_at).exists():
                logger.info(
                    "Processed duplicate observation %s", das_obs.subject_subtype, extra={"obs.dup": provider_key}
                )
                continue

            observation = {
                "location": das_obs.location,
                "recorded_at": das_obs.recorded_at,
                "source": str(src.id),
                "additional": das_obs.additional,
            }

            serializer = ObservationSerializer(data=observation)
            if serializer.is_valid():
                serializer.save()
                logger.info("Added new observation %s", observation, extra={"obs.new": provider_key})
                notify_new_tracks(src.id)
            else:
                logger.info("An error occured whle serializing the observation: %s", serializer.errors)
        status_ok = {"status": 0, "message": "success"}
        return Response(data=status_ok, status=status.HTTP_200_OK)


class TractVehicleHandler:
    SENSOR_TYPE = "vehicle-observation"
    DEFAULT_SUBJECT_SUBTYPE = "truck"
    serializer_class = TractVehicleData

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info("Recieved new push message %s", request.data)
        params = TractVehicleData.parse_observations(request.data)

        if not params.is_valid():
            status_fail = {"status": 404, "message": params.errors}
            return Response(data=status_fail, status=status.HTTP_200_OK)

        else:
            adapter = TractAdapter()
            # need to 'unbind' these values
            mfg_id = params["MfgId"].value
            reg = params["Reg"].value

            for observation in params.data["Records"]:
                das_obs = adapter.create_das_object(mfg_id, reg, observation)
                src = Source.objects.ensure_source(
                    das_obs.source_type,
                    provider=provider_key,
                    manufacturer_id=das_obs.manufacturer_id,
                    model_name=das_obs.model_name,
                    subject={"subject_subtype_id": das_obs.subject_subtype, "name": das_obs.subject_name},
                )
                # skip if we already have this observation.
                if Observation.objects.filter(source=src, recorded_at=das_obs.recorded_at).exists():
                    logger.info(
                        "Processed duplicate observation %s", das_obs.subject_subtype, extra={"obs.dup": provider_key}
                    )
                    continue

                observation = {
                    "location": das_obs.location,
                    "recorded_at": das_obs.recorded_at,
                    "source": str(src.id),
                    "additional": das_obs.additional,
                }

                serializer = ObservationSerializer(data=observation)
                if serializer.is_valid():
                    serializer.save()
                    logger.info("Added new observation %s", observation, extra={"obs.new": provider_key})
                    notify_new_tracks(src.id)
                else:
                    logger.info("An error occured whle serializing the observation: %s", serializer.errors)

        status_ok = {"status": 200, "message": "success"}

        return Response(data=status_ok, status=status.HTTP_200_OK)


class SigFoxCallback(serializers.Serializer):
    device = serializers.CharField()
    time = serializers.IntegerField()
    loc = serializers.DictField()


class SigFoxPushHandler:
    SENSOR_TYPE = "sf-animal-tracker"
    SOURCE_TYPE = "tracking-device"
    MODEL_NAME = "DigitAnimal"
    serializer_class = SigFoxCallback

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        params = SigFoxCallback(data=request.data)

        logger.info("Sigfox observation %s", request.data, extra={"obs.new": request.data})

        if not params.is_valid():
            resp = Response(data={"status": 404, "message": params.errors}, status=status.HTTP_400_BAD_REQUEST)
        else:
            device_id = params["device"]

            src, created = Source.objects.ensure_source(
                cls.SOURCE_TYPE,
                provider=provider_key,
                manufacturer_id=device_id,
                model_name="{}:{}".format(sensor_type, provider_key),
            )

        status_ok = {"status": 200, "message": "success", "handler": "sigfox-push"}

        return Response(data=status_ok, status=status.HTTP_201_OK)


class GateHandler:
    SENSOR_TYPE = "gate"

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info(
            f"{sensor_type} observation {request.data} for provider {provider_key}",
            extra={"data": request.data, "provider_key": provider_key, "sensor_type": sensor_type},
        )

        status_ok = {"status": 200, "message": "success", "handler": f"{sensor_type}"}

        return Response(data=status_ok, status=status.HTTP_200_OK)


class TestHandler:
    SENSOR_TYPE = "test"

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info(
            f"{sensor_type} observation {request.data} for provider {provider_key}",
            extra={"data": request.data, "provider_key": provider_key, "sensor_type": sensor_type},
        )

        status_ok = {"status": 200, "message": "success", "handler": f"{sensor_type}"}

        return Response(data=status_ok, status=status.HTTP_200_OK)


class GFWAlertHandler:
    SENSOR_TYPE = "gfw-alert"
    PROVIDER_KEY = "gfw"
    serializer_class = gfw_inbound.GFWAlertParameters

    @classmethod
    def post(cls, request, provider_key):
        return gfw_inbound.process_handler_post(request)


class EzyTrackHandler:
    SENSOR_TYPE = "ezytrack-tracker"
    serializer_class = EzytrackObservation

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info(f"Received new push message {request.data}")

        serializer_ = EzytrackObservation(data=request.data)
        if not serializer_.is_valid():
            status_msg = {"status": 400, "message": serializer_.errors}
            return Response(data=status_msg, status=status.HTTP_400_BAD_REQUEST)
        else:
            adapter = EzyTrackAdapter()
            das_observation = adapter.create_das_object(serializer_.data)

            src = Source.objects.ensure_source(
                das_observation.source_type,
                provider=provider_key,
                manufacturer_id=das_observation.manufacturer_id,
                model_name=das_observation.model_name,
                subject={"subject_subtype_id": das_observation.subject_subtype, "name": das_observation.subject_name},
            )
            if Observation.objects.filter(source=src, recorded_at=das_observation.recorded_at).exists():
                logger.info("Processed duplicate observation {}".format(das_observation))
                return Response(data={}, status=status.HTTP_200_OK)
            else:
                observation = {
                    "location": das_observation.location,
                    "recorded_at": das_observation.recorded_at,
                    "source": str(src.id),
                    "additional": das_observation.additional,
                }

                observation_serializer = ObservationSerializer(data=observation)
                if observation_serializer.is_valid():
                    observation_serializer.save()
                    logger.debug("New observation added. %s" % observation)
                    notify_new_tracks(src.id)
                else:
                    logger.debug("Error occured while serializing observation: %s " % observation_serializer.errors)
                    status_msg = {"status": 400, "message": observation_serializer.errors}
                    return Response(data=status_msg, status=status.HTTP_400_BAD_REQUEST)

        status_ok = {"status": 201, "message": "Success"}
        return Response(data=status_ok, status=status.HTTP_201_CREATED)


class PointDictSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    altitude = serializers.FloatField()
    gpsFix = serializers.IntegerField()
    course = serializers.FloatField()
    speed = serializers.FloatField()


class InreachEventSerializer(serializers.Serializer):
    imei = serializers.IntegerField()
    messageCode = serializers.IntegerField()
    timeStamp = serializers.IntegerField()
    addresses = serializers.ListField()
    status = serializers.DictField()
    point = PointDictSerializer()


class InreachObservation(serializers.Serializer):
    Events = serializers.ListField(child=InreachEventSerializer())


class InreachPushHandler:
    SENSOR_TYPE = "inreach-tracker"
    subject_type = "person"
    subject_subtype = "ranger"
    model_name = "InReach"
    source_type = "gps-radio"
    serializer_class = InreachObservation

    @classmethod
    def post(cls, request, provider_key, sensor_type=None):
        if not sensor_type:
            sensor_type = cls.SENSOR_TYPE

        logger.info("Recieved new push message %s", request.data)
        cls.provider_key = provider_key
        cls.new_observations = 0

        serializer = InreachObservation(data=request.data)
        if not serializer.is_valid():
            return Response(data={"status": 400, "message": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        else:
            for data in serializer.data.get("Events"):
                das_obs = cls.create_das_object(data)
                cls.ensure_source(das_obs)
                cls.create_observation(das_obs)

            if cls.new_observations:
                return Response(
                    data={"message": f"{cls.new_observations} new observation(s) added"}, status=status.HTTP_200_OK
                )
            else:
                return Response(data={}, status=status.HTTP_200_OK)

    @classmethod
    def create_das_object(cls, data):
        point = data.get("point")
        obs = DasObservation(
            location={"latitude": point.pop("latitude"), "longitude": point.pop("longitude")},
            recorded_at=datetime.fromtimestamp(data.get("timeStamp") / 1000, timezone.utc),
            manufacturer_id=data.get("imei"),
            subject_name=data.get("imei"),
            subject_type=cls.subject_type,
            subject_subtype=cls.subject_subtype,
            model_name=cls.model_name,
            source_type=cls.source_type,
            additional=data,
        )
        return obs

    @classmethod
    def ensure_source(cls, obs):
        """Get or create provider, source and subject"""

        cls.src = Source.objects.ensure_source(
            source_type=obs.source_type,
            model_name=obs.model_name,
            provider=cls.provider_key,
            manufacturer_id=obs.manufacturer_id,
            subject={
                "subject_subtype_id": obs.subject_subtype,
                "name": obs.subject_name,
            },
        )

    @classmethod
    def create_observation(cls, observation):
        """Create observation, ignore duplicates"""
        if Observation.objects.filter(recorded_at=observation.recorded_at, source=cls.src).exists():
            logger.info(f"Skipping duplicate observation from {cls.src}")
        else:
            observation = {
                "location": observation.location,
                "recorded_at": observation.recorded_at,
                "source": str(cls.src.id),
                "additional": observation.additional,
            }
            serializer = ObservationSerializer(data=observation)

            if serializer.is_valid():
                serializer.save()
                cls.new_observations += 1
                logger.info(f"New observation created from source {cls.src}")
            else:
                logger.error(f"Invalid observation records {serializer.errors}")
