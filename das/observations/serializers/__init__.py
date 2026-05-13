import logging
import re
from collections import OrderedDict
from datetime import MAXYEAR, MINYEAR, datetime, timezone
from typing import NamedTuple

from drf_extra_fields.fields import DateTimeRangeField
from drf_extra_fields.geo_fields import PointField
from rest_framework_gis.serializers import GeoFeatureModelListSerializer

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import jsonb
from django.db.models import Q
from django.urls import reverse
from rest_framework import serializers
from rest_framework.fields import DateTimeField

import utils.json
from accounts.serializers import UserDisplaySerializer
from buoy.constants import BUOY_GEAR_SUBJECT_SUBTYPE
from core.fields import GEOPointField, choicefield_serializer, text_field
from core.serializers import (
    BaseSerializer,
    ContentTypeField,
    GenericRelatedField,
    TimestampMixin,
)
from observations import models
from observations.models import (
    STATIONARY_SUBJECT_VALUE,
    SubjectSource,
    transform_additional_data,
)
from observations.services import (
    get_observation_coordinates_and_times_by_subject_id_and_source_id,
)
from observations.utils import (
    VIEW_SUBJECT_PERMS,
    dateparse,
    get_maximum_allowed_age,
    get_minimum_allowed_age,
    get_null_point,
    is_subject_stationary_subject,
)
from utils import add_base_url
from utils.serializers import PartialUpdateMixin

from .observations import FlattenObservationSerializer

logger = logging.getLogger(__name__)


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Region
        fields = ("slug", "region", "country")


class RecursiveSerializer(serializers.Serializer):
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(instance, context=self.context)
        return serializer.data


def create_sg_serializer(name, model, serializer, include_subgroups=True):
    contained_field = "{0}s".format(serializer.Meta.model._meta.model_name)
    meta_fields = ("name", "id")
    if include_subgroups:
        meta_fields += ("subgroups",)
    meta = type("Meta", (object,), dict(model=model, fields=meta_fields))

    gs_fields = dict(serializer=serializer, Meta=meta, contained_field=contained_field)
    if include_subgroups:
        gs_fields["subgroups"] = RecursiveSerializer(many=True, read_only=True, source="children")

    return type(name, (GroupSerializer,), gs_fields)


class GroupSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        user = getattr(self.context.get("request", None), "user", None)
        data_serializer = self.serializer(context=self.context)
        contained_field = self.contained_field

        include_inactive = self.context["request"].GET.get("include_inactive", None)

        mou_date = user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None

        queryset = getattr(instance, "get_all_{0}".format(contained_field))(
            user=user, include_inactive=include_inactive, include_from_subgroups=False, mou_expiry_date=mou_date
        )

        # queryset = queryset.order_by('name')
        # queryset variable contains list of sources linked with source group.
        # name is not a field of source object but model_name is.
        # queryset = sorted(queryset, key=lambda k: k.model_name, reverse=False)
        rep = super().to_representation(instance)
        data = [data_serializer.to_representation(s) for s in queryset]
        rep[contained_field] = data
        return rep


def get_subject_display(subject):
    return subject.name


class SubjectTypeRelatedField(serializers.RelatedField):
    def get_queryset(self):
        return models.SubjectType.objects.all()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return models.SubjectType.objects.get(value=data)
            except models.SubjectType.DoesNotExist:
                raise serializers.ValidationError(f"subject_type : {data} does not exist")


class SubjectSubTypeRelatedField(serializers.RelatedField):
    def get_queryset(self):
        return models.SubjectSubType.objects.all()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return models.SubjectSubType.objects.get(value=data)
            except models.SubjectSubType.DoesNotExist:
                raise serializers.ValidationError(f"subject_subtype : {data} does not exist")


class CommonNameRelatedField(serializers.RelatedField):
    def get_queryset(self):
        return models.CommonName.objects.all()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return models.CommonName.objects.get(value=data)
            except models.CommonName.DoesNotExist:
                raise serializers.ValidationError(f"common_name : {data} does not exist")


class TimezoneOverflowAwareDateTimeField(DateTimeField):
    def enforce_timezone(self, value):
        """we wont enforce timezone on datetime object with max year number or min year number; to prevent OverFlow"""
        if value.year >= MAXYEAR or value.year <= MINYEAR:
            return value
        else:
            return super().enforce_timezone(value)


class SubjectSourceSerializer(serializers.ModelSerializer):
    assigned_range = DateTimeRangeField(child=TimezoneOverflowAwareDateTimeField())
    location = PointField(required=False)

    class Meta:
        model = SubjectSource
        fields = ("id", "assigned_range", "source", "subject", "additional", "location")

    def create(self, validated_data):
        return SubjectSource.objects.ensure(
            subject=validated_data["subject"],
            source=validated_data["source"],
            assigned_range=validated_data["assigned_range"],
            location=validated_data.get("location", None),
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if not is_subject_stationary_subject(instance.subject):
            representation["location"] = None
        return representation


class LinkedUserserializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id",)


class SubjectSerializer(PartialUpdateMixin, serializers.Serializer):
    content_type = ContentTypeField(read_only=True, required=False)

    id = serializers.UUIDField(
        required=False,
    )
    name = serializers.CharField(max_length=100)
    subject_type = serializers.CharField(max_length=100, required=False, read_only=True)
    subject_subtype = SubjectSubTypeRelatedField()
    common_name = CommonNameRelatedField(required=False)
    additional = serializers.JSONField(label="Additional data", required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    is_active = serializers.BooleanField(required=False)
    user = LinkedUserserializer(source="linked_user", read_only=True)

    additional_fields = ("region", "country", "sex", "species", "additional")

    allowed_partial_update_fields = ("name", "subject_subtype", "common_name", "additional", "is_active")
    partial_update_side_effects = [
        "updated_at",
    ]

    class Meta:
        model = models.Subject
        read_only_fields = (
            "image_url",
            "color",
            "content_type",
            "subject_type",
            "user",
        )
        fields = (
            "id",
            "name",
            "subject_subtype",
            "common_name",
            "additional",
            "is_active",
        ) + read_only_fields

    def to_internal_value(self, data):
        if "id" in data and self.read_only:
            try:
                return models.Subject.objects.get(id=data["id"])
            except models.Subject.DoesNotExist:
                raise serializers.ValidationError(f"Subject: {data} does not exist.")
        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        render_last_location = self.context.get("render_last_location", True)
        show_track_days_since = self.context.get("show_track_days_since", datetime.min.replace(tzinfo=timezone.utc))
        user = getattr(request, "user", None)

        # For buoy gear subjects, use the source's manufacturer_id as the name
        if instance.subject_subtype_id == BUOY_GEAR_SUBJECT_SUBTYPE:
            rep["name"] = self._get_buoy_gear_display_name(instance)

        additional = instance.additional
        additional = {k: additional[k] for k in self.additional_fields if k in additional}
        rep.update(additional)
        rep["tracks_available"] = False
        rep["image_url"] = instance.image_url
        is_stationary_subject = self._is_stationary_subject(instance)
        if is_stationary_subject:
            rep["is_static"] = True

        if user and render_last_location:
            # Find the user's allowed viewable date range
            maximum_allowed_age = get_maximum_allowed_age(user)
            minimum_allowed_age = get_minimum_allowed_age(user)
            # additional.get('expiry', None)
            mou_expiry_date = user.mou_expiry_date

            if mou_expiry_date is not None:
                if not mou_expiry_date.tzinfo:
                    mou_expiry_date = mou_expiry_date.replace(tzinfo=timezone.utc)

                mou_expiry_age = datetime.now(tz=timezone.utc) - mou_expiry_date

                minimum_allowed_age = max(mou_expiry_age.days, minimum_allowed_age)
                if maximum_allowed_age < minimum_allowed_age:
                    maximum_allowed_age = None
                    minimum_allowed_age = None

            if minimum_allowed_age is not None and maximum_allowed_age is not None:
                statusvalues = resolve_status_values(instance)

                # Get last_position details from latest accessible source
                # according to SourceGroup permissions.
                linked_sources = self.context.get("subject_linked_sources", {}).get(instance.id)
                if linked_sources:
                    # Fetch latest Observations available to plot
                    # latest_position & tracks_range.
                    latest_source = linked_sources["latest_source"]
                    latest_range = linked_sources["latest_range"]

                    if latest_range:
                        query = models.Observation.objects.get_source_observations(
                            source=latest_source,
                            since=latest_range.lower,
                            until=latest_range.upper,
                            include_empty_location=False,
                            order_by="-recorded_at",
                        )
                        latest_observation = query.first()

                        if latest_observation and latest_observation.recorded_at >= show_track_days_since:
                            additional = latest_observation.additional
                            if not isinstance(additional, dict):
                                additional = {}
                            # Construct a response with latest_location
                            # details.
                            rep["tracks_available"] = True
                            rep["last_position_status"] = {
                                "last_voice_call_start_at": additional.get("last_voice_call_start_at"),
                                "radio_state_at": additional.get("radio_state_at"),
                                "radio_state": additional.get("radio_state"),
                            }
                            rep["last_position_date"] = latest_observation.recorded_at

                            location = latest_observation.location
                            if is_stationary_subject and instance.latest_subjectsource_location:
                                location = instance.latest_subjectsource_location

                            rep["last_position"] = make_feature(
                                request,
                                location,
                                instance,
                                time=latest_observation.recorded_at,
                                image_url=rep["image_url"],
                            )
                else:
                    # If no linked_sources are available then fetch
                    # latest_position from SubjectStatus as usual.

                    if (
                        mou_expiry_date
                        and (mou_expiry_date.replace(tzinfo=timezone.utc) <= datetime.now(tz=timezone.utc))
                        and request.method == "GET"
                    ):
                        observation = get_observation_location(instance, mou_expiry_date)
                        location = observation.location if observation else get_null_point()
                        recorded_at = observation.recorded_at if observation else None
                    else:
                        location = statusvalues.location if statusvalues.location else get_null_point()
                        recorded_at = statusvalues.recorded_at

                    tracks_available = bool(
                        recorded_at
                        and recorded_at != models.DEFAULT_STATUS_VALUE_DATE
                        and recorded_at >= show_track_days_since
                    )
                    rep["tracks_available"] = tracks_available
                    rep["last_position_status"] = {
                        "last_voice_call_start_at": (
                            None
                            if statusvalues.last_voice_call_start_at == models.DEFAULT_STATUS_VALUE_DATE
                            else statusvalues.last_voice_call_start_at
                        ),
                        "radio_state_at": (
                            None
                            if statusvalues.radio_state_at == models.DEFAULT_STATUS_VALUE_DATE
                            else statusvalues.radio_state_at
                        ),
                        "radio_state": statusvalues.radio_state,
                    }
                    if is_stationary_subject and instance.latest_subjectsource_location:
                        location = instance.latest_subjectsource_location

                    if tracks_available:
                        rep["last_position_date"] = recorded_at
                        rep["last_position"] = make_feature(
                            request, location, instance, time=recorded_at, image_url=rep["image_url"]
                        )

                rep["device_status_properties"] = self._get_device_status_properties(statusvalues)
                if is_stationary_subject:
                    rep["device_status_properties"] = self._get_device_properties_static_sensor(statusvalues, instance)
                    rep["tracks_available"] = False

                # Add buoy gear specific properties to last_position if applicable
                if "last_position" in rep:
                    display_name, additional, _ = self._get_buoy_gear_feature_props(
                        instance, rep.get("device_status_properties")
                    )
                    if display_name:
                        rep["last_position"]["properties"]["name"] = display_name
                    if additional:
                        rep["last_position"]["properties"]["additional"] = additional
                    if rep.get("device_status_properties"):
                        rep["last_position"]["properties"]["device_status_properties"] = rep["device_status_properties"]

        if request:
            rep["url"] = utils.add_base_url(
                request,
                reverse(
                    "subject-view",
                    args=[
                        instance.id,
                    ],
                ),
            )

            message_content = []

            # for ss in get_subjectsources_with_2way_msg(instance):
            if "two_way_subject_sources" in self.context.keys():
                # two_way_subject_sources is a dict by source_id
                two_way_subject_sources = self.context["two_way_subject_sources"]
                instance_id = instance.id
                for subject_source in [
                    ss_for_subject
                    for ss_by_source in two_way_subject_sources.values()
                    for ss_for_subject in ss_by_source.values()
                    if ss_for_subject["subject_id"] == instance_id
                ]:
                    message_url = utils.add_base_url(request, reverse("messages-view"))
                    data = {
                        "source_provider": subject_source["source__provider__display_name"],
                        "url": f"{message_url}?subject_id={str(instance.id)}&source_id={str(subject_source['source_id'])}",
                    }
                    message_content.append(data)

            if message_content:
                rep["messaging"] = message_content

        if self.context.get("tracks", False):
            track_serializer = SubjectTrackSerializer(instance, context=self.context)
            rep["tracks"] = track_serializer.data

        return rep

    def create(self, validated_data):
        if "request" in self.context:
            request = self.context["request"]
            validated_data["owner"] = request.user

        return models.Subject.objects.create_subject(**validated_data)

    def _is_stationary_subject(self, instance):
        if instance.subject_type == STATIONARY_SUBJECT_VALUE and getattr(
            instance, "latest_subjectsource_exists", False
        ):
            return True
        return False

    def _get_device_status_properties(self, status_values):
        if hasattr(status_values, "device_status_properties"):
            return status_values.device_status_properties
        return None

    def _get_device_properties_static_sensor(self, status_values, subject):
        device_status_properties = self._get_device_status_properties(status_values)
        default_measure = self._get_default_measure(subject)
        if device_status_properties:
            for device in device_status_properties:
                device["default"] = False
                if device.get("label") == default_measure:
                    device["default"] = True
        return device_status_properties

    def _get_default_measure(self, subject):
        if not hasattr(subject, "latest_subjectsource_transforms"):
            raise ValueError("Subject does not have latest_subjectsource_transforms annotation")
        if transforms := getattr(subject, "latest_subjectsource_transforms", None):
            for transform in transforms:
                if transform.get("default"):
                    return transform.get("label")
        return ""

    # Pattern to match device identifier like "88CE99DC88" (alphanumeric, 6-20 chars)
    BUOY_DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{6,20}$")

    def _get_buoy_gear_display_name(self, subject):
        """Get the display name for buoy gear subjects using the source's manufacturer_id.

        The manufacturer_id may be in the format "88CE99DC88_EVG6q84wwjTqvYlPg00BF9EJpWK99zh6pAmRJ80j_A"
        where we only want to display the first segment before the underscore: "88CE99DC88"

        If the first segment doesn't match the expected device ID pattern, falls back to subject name.

        Performance note: Prefers using 'latest_source_manufacturer_id' annotation if available
        (set by annotate_with_subjectsource_transforms) to avoid N+1 queries when serializing lists.
        """
        manufacturer_id = self._get_manufacturer_id(subject)
        if manufacturer_id:
            # Extract the first segment before the underscore (e.g., "88CE99DC88" from "88CE99DC88_xxx_yyy")
            first_segment = manufacturer_id.split("_")[0]
            # Validate the first segment matches expected device ID pattern
            if self.BUOY_DEVICE_ID_PATTERN.match(first_segment):
                return first_segment
        # Fall back to the subject's name if no valid device ID found
        return subject.name

    def _get_manufacturer_id(self, subject):
        """Get manufacturer_id from annotation or query, preferring annotation for performance."""
        # First, try to use the annotation (avoids N+1 queries in list views)
        if hasattr(subject, "latest_source_manufacturer_id") and subject.latest_source_manufacturer_id:
            return subject.latest_source_manufacturer_id

        # Fall back to querying (for single subject views or when annotation is missing)
        subject_source = subject.subjectsources.select_related("source").order_by("-assigned_range").first()
        if subject_source and subject_source.source:
            return subject_source.source.manufacturer_id
        return None

    def _get_provider_display_name(self, subject):
        """Get manufacturer name from subject.additional, annotation, or source provider."""
        additional = getattr(subject, "additional", None) or {}
        manufacturer = additional.get("manufacturer")
        if manufacturer:
            return manufacturer

        # Fall back to annotation (avoids N+1 queries in list views)
        if hasattr(subject, "latest_source_provider_display_name") and subject.latest_source_provider_display_name:
            return subject.latest_source_provider_display_name

        # Fall back to querying source provider
        subject_source = subject.subjectsources.select_related("source__provider").order_by("-assigned_range").first()
        if subject_source and subject_source.source and subject_source.source.provider:
            return subject_source.source.provider.display_name
        return None

    def _get_buoy_gear_feature_props(self, subject, device_status_properties=None):
        """Get buoy gear specific properties for GeoJSON features.

        Returns a tuple of (display_name, additional, device_status_properties) for buoy gear subjects,
        or (None, None, None) for non-buoy subjects.
        """
        if subject.subject_subtype_id != BUOY_GEAR_SUBJECT_SUBTYPE:
            return None, None, None

        # Get the parsed display name (first segment of manufacturer_id)
        display_name = self._get_buoy_gear_display_name(subject)
        # If display_name equals subject.name, it means we fell back (no valid manufacturer_id)
        if display_name == subject.name:
            display_name = None

        # Build additional properties
        additional = {
            "display_id": str(subject.id),
        }
        manufacturer = self._get_provider_display_name(subject)
        if manufacturer:
            additional["manufacturer"] = manufacturer

        return display_name, additional, device_status_properties


class SubjectIdSerializer(serializers.Serializer):
    """Serializer for a single subject ID."""

    id = serializers.UUIDField(help_text="Subject UUID to add to the group")

    def validate(self, value):
        """Validate that all subject IDs exist and are accessible to the user."""
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("User context is required.")

        user = request.user

        # Extract subject IDs from the subject objects
        subject_ids = [value.get("id")] if isinstance(value, dict) else [item.get("id") for item in value]

        if not subject_ids:
            raise serializers.ValidationError("No valid subject IDs provided.")

        existing_subjects = models.Subject.objects.filter(id__in=subject_ids)

        # Check if all subjects exist
        if len(existing_subjects) != len(subject_ids):
            existing_ids = {str(subject.id) for subject in existing_subjects}
            missing_ids = [str(subject_id) for subject_id in subject_ids if str(subject_id) not in existing_ids]
            raise serializers.ValidationError(f"Subjects with IDs {missing_ids} do not exist.")

        # Check permissions for each subject
        if not user.has_any_perms(VIEW_SUBJECT_PERMS):
            # If user doesn't have general subject permissions, check if they're linked to these subjects
            linked_subjects = models.Subject.objects.filter(linked_user=user, id__in=subject_ids)
            if len(linked_subjects) != len(subject_ids):
                raise serializers.ValidationError("You don't have permission to access all the specified subjects.")

        return value


class SubjectRelatedField(serializers.RelatedField):
    def to_representation(self, value):
        rep = SubjectSerializer().to_representation(value)
        return rep

    def to_internal_value(self, data):
        return SubjectSerializer(read_only=True).to_internal_value(data)

    def get_queryset(self):
        return models.Subject.objects.all()


def get_subjectsources_with_2way_msg(subject):
    """filter based on messaging capabilities that are attached to either source or source-provider
    link to truth table. https://vulcan.atlassian.net/browse/DAS-6713?focusedCommentId=70634
    """
    condition = Q(two_way_messaging=True) & (Q(source_two_way_messaging=False, source_two_way_messaging__isnull=False))

    subject_sources = (
        models.SubjectSource.objects.filter(subject=subject)
        .annotate(
            two_way_messaging=jsonb.KeyTransform("two_way_messaging", "source__provider__additional"),
            source_two_way_messaging=jsonb.KeyTransform("two_way_messaging", "source__additional"),
        )
        .exclude(Q(two_way_messaging__isnull=True) | Q(two_way_messaging=False) | condition)
    )
    return subject_sources


class SubjectGeoJsonSerializer(SubjectSerializer):
    @classmethod
    def many_init(cls, *args, **kwargs):
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {"child": child_serializer}
        list_kwargs.update(
            dict([(key, value) for key, value in kwargs.items() if key in serializers.LIST_SERIALIZER_KWARGS])
        )
        meta = getattr(cls, "Meta", None)
        list_serializer_class = getattr(meta, "list_serializer_class", GeoFeatureModelListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    def create(self, validated_data):
        raise NotImplemented("Create subject using GeoJson not supported")

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        subject = rep.get("last_position", None)
        if not subject:
            subject = make_feature(self.context["request"], None, instance, time=None, image_url=rep["image_url"])
        return subject


class SubjectStatusValues(NamedTuple):
    recorded_at: datetime
    location: Point
    radio_state: str
    radio_state_at: datetime
    last_voice_call_start_at: datetime
    device_status_properties: dict


def resolve_status_values(subject):
    """
    Parse subject-status values from
    :param subject:
    :return:
    """
    if hasattr(subject, "status_radio_state"):
        return SubjectStatusValues(
            **dict((k, getattr(subject, f"status_{k}", None)) for k in SubjectStatusValues._fields)
        )
    try:
        return models.SubjectStatus.objects.get_current_status(subject)
    except models.SubjectStatus.DoesNotExist:
        raise ValueError(f"SubjectStatus does not exist for subject ID: {subject.id}")


def get_observation_location(subject, mou_date):
    """Return the latest subject observation less than the date of expiry,
    and more recent than the site window cutoff

    Args:
        subject ([Subject]): observation subject
        mou_date ([datetime]): user mou expiry
    Returns:
        [Observation]: the observation
    """

    observation = models.Observation.objects.get_subject_observations_partitioned(
        subject, until=mou_date, order_by="-recorded_at"
    ).first()

    return observation


class SourceProviderRelatedField(serializers.RelatedField):
    def get_queryset(self):
        return models.SourceProvider.objects.all()

    def to_representation(self, value):
        return value.provider_key if value else None

    def to_internal_value(self, data):
        if data:
            try:
                return models.SourceProvider.objects.get(provider_key=data)
            except models.SourceProvider.DoesNotExist:
                raise serializers.ValidationError({"provider_key": "Value '%s' does not exist." % data})
        return None

    @property
    def choices(self):
        return OrderedDict(((row.provider_key, row.display_name) for row in self.get_queryset()))


class SourceSerializer(PartialUpdateMixin, serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    source_type = serializers.ChoiceField(
        allow_null=True,
        choices=(
            ("tracking-device", "Tracking Device"),
            ("trap", "Trap"),
            ("seismic", "Seismic sensor"),
            ("firms", "FIRMS data"),
            ("gps-radio", "gps radio"),
        ),
        label="Type of data expected",
        required=False,
    )
    manufacturer_id = serializers.CharField(
        allow_null=True, label="Device manufacturer id", max_length=100, required=False
    )
    model_name = serializers.CharField(allow_null=True, label="Device model name", max_length=100, required=False)
    additional = serializers.JSONField(label="Additional data")
    provider = SourceProviderRelatedField()
    subject = SubjectRelatedField(label="Subject data", required=False)
    content_type = ContentTypeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    allowed_partial_update_fields = ("source_type", "manufacturer_id", "model_name", "additional", "provider")
    partial_update_side_effects = [
        "updated_at",
    ]

    class Meta:
        model = models.Source
        fields = ("id", "source_type", "manufacturer_id", "model_name", "additional", "provider", "owner")

    def to_representation(self, instance):
        rep = super(SourceSerializer, self).to_representation(instance)
        rep.update(instance.additional)
        try:
            subject_sources = self.context["view"].two_way_subject_sources
            subject_source = subject_sources.get(source=instance)
            rep["assigned_range"] = subject_source.assigned_range
        except (AttributeError, KeyError):
            pass

        if "request" in self.context:
            request = self.context["request"]

            rep["url"] = utils.add_base_url(
                request,
                reverse(
                    "source-view",
                    args=[
                        instance.id,
                    ],
                ),
            )

        return rep

    def create(self, validated_data):
        if "request" in self.context:
            request = self.context["request"]
            validated_data["owner"] = request.user

        source, created = models.Source.objects.get_source(**validated_data)
        return source


class SourceProviderSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    provider_key = serializers.CharField(label="Source Provider Value", max_length=100, required=True)
    display_name = serializers.CharField(
        label="Display Name",
        max_length=100,
    )
    additional = serializers.JSONField(
        label="Additional Data",
    )

    class Meta:
        model = models.SourceProvider
        fields = ("id", "provider_key", "display_name", "additional")

    def create(self, validated_data):
        instance = models.SourceProvider.objects.create_provider(**validated_data)
        return instance

    def update(self, instance, validated_data):
        instance.provider_key = validated_data.get("provider_key", instance.provider_key)
        instance.display_name = validated_data.get("display_name", instance.display_name)
        instance.additional = validated_data.get("additional", instance.additional)
        instance.save()
        return instance


class SubjectTrackSerializer(serializers.Serializer):
    def to_representation(self, subject):
        image_url = subject.image_url
        user = self.context["request"].user
        tracks_since = self.context.get("tracks_since", None)
        tracks_until = self.context.get("tracks_until", None)
        tracks_limit = self.context.get("tracks_limit", None)

        subject_linked_sources = self.context.get("subject_linked_sources")
        linked_sources = []
        if isinstance(subject_linked_sources, dict):
            subject_data = subject_linked_sources.get(subject.id) or {}
            source_id = subject_data.get("latest_source")
            if source_id:
                linked_sources.append(source_id)
        elif subject_linked_sources:
            linked_sources = [source.id for source in subject_linked_sources]

        if linked_sources:
            coordinates = []
            times = []
            # Fetch Observations only from the linked sources to limit view
            # on a Source level
            for source_id in linked_sources:
                data = get_observation_coordinates_and_times_by_subject_id_and_source_id(subject.id, source_id)
                coordinates.extend(data["coordinates"])
                times.extend(data["times"])
        else:
            coordinates, times = subject.get_track(user, tracks_since, tracks_until, tracks_limit)

        feature = make_feature(self.context["request"], coordinates, subject, times, image_url=image_url)

        rep = utils.json.empty_geojson_featurecollection()
        rep["features"].append(feature)

        return rep


class SubjectStatusSerializer(serializers.Serializer):
    def to_representation(self, subject_status):
        coordinates = Point(x=subject_status.location.x, y=subject_status.location.y, srid=4326)

        feature = make_subjectstatus_feature(self.context["request"], coordinates, subject_status)

        feature["device_status_properties"] = subject_status.additional.get("device_status_properties")

        return feature


class TrackSerializer(serializers.Serializer):
    def to_representation(self, instance):
        # TODO: Review with Shawn, wrt to recent changes in SubjectTracksView.
        image_url = (self.context.get("subject") or instance).image_url

        feature = make_feature(
            self.context["request"], self.context["coordinates"], instance, self.context["times"], image_url=image_url
        )
        rep = utils.json.empty_geojson_featurecollection()
        rep["features"].append(feature)

        return rep


class SourceRelatedField(serializers.RelatedField):
    def get_queryset(self):
        return models.Source.objects.select_related("provider").all()

    def to_representation(self, source):
        """
        :param source:
        :return: dict representation of this related source.
        """
        return source.id

    def to_internal_value(self, data):
        if not data:
            return None

        # If we're just passed a string, then treat it as an ID value.
        if isinstance(data, str):
            try:
                return models.Source.objects.get(id=data)
            except models.Source.DoesNotExist:
                return None


class ObservationSerializer(serializers.ModelSerializer):
    source = serializers.UUIDField(source="source_id")
    location = PointField(required=False)
    source_transforms = serializers.JSONField(required=False)

    class Meta:
        model = models.Observation
        fields = (
            "id",
            "location",
            "created_at",
            "recorded_at",
            "additional",
            "source",
            "source_transforms",
            "exclusion_flags",
        )
        id_field = False
        geo_field = "location"

    def to_representation(self, instance):
        rep = super(ObservationSerializer, self).to_representation(instance)
        query_params = self.context.get("request").query_params if self.context.get("request") else {}
        self.dict_to_representation(rep, query_params)
        return rep

    @staticmethod
    def dict_to_representation(rep, params):
        if not rep.get("source"):
            rep["source"] = rep.pop("source_id")

        if rep.get("source_transforms") and rep.get("additional"):
            rep["device_status_properties"] = transform_additional_data(rep["additional"], rep["source_transforms"])

        if params.get("include_details"):
            # and adding observation details if requested.
            rep["observation_details"] = rep["additional"]

        location = rep.get("location")
        if location and not isinstance(location, dict):
            rep["location"] = dict(longitude=location.x, latitude=location.y)

        rep.pop("additional", None)
        rep.pop("source_transforms", None)
        return rep


SUBJECT_STATUS_RETURN_FIELDS = ("last_voice_call_start_at", "location_requested_at", "radio_state_at") + (
    "radio_state",
)


def make_subjectstatus_feature(request, location: Point, subjectstatus):
    image_url = add_base_url(request, subjectstatus.subject.image_url)

    feature = {
        "geometry": {"type": "Point", "coordinates": location.tuple},
        "type": "Feature",
        "properties": {
            "id": subjectstatus.subject_id,
            "name": subjectstatus.subject.name,
            "type": subjectstatus.subject.subject_subtype.subject_type.value,
            "subtype": subjectstatus.subject.subject_subtype.value,
            "image": image_url,
            "state": subjectstatus.radio_state,
            "coordinateProperties": {"time": subjectstatus.recorded_at},
        },
    }

    for k in ("last_voice_call_start_at", "location_requested_at", "radio_state_at"):
        val = getattr(subjectstatus, k, None)
        if val:
            feature["properties"][k] = val

    return feature


def make_feature(
    request,
    coordinates,
    subject,
    coordinate_times=None,
    time=None,
    image_url=None,
    display_name=None,
    additional=None,
    device_status_properties=None,
):
    """Create a GeoJSON feature for a subject.

    Args:
        request: The HTTP request object.
        coordinates: Point or list of coordinates for the feature geometry.
        subject: The Subject instance.
        coordinate_times: List of times for LineString coordinates.
        time: Time for Point coordinates.
        image_url: Optional image URL override.
        display_name: Optional display name to use as 'name' property (e.g., parsed manufacturer_id).
        additional: Optional dict of additional properties to include.
        device_status_properties: Optional device status properties to include.

    Returns:
        dict: A GeoJSON Feature object.
    """
    is_point = isinstance(coordinates, Point)
    image_url = add_base_url(request, image_url or subject.image_url)
    feature = {
        "type": "Feature",
        "geometry": None,
        "properties": {
            "title": subject.name,
            "subject_type": subject.subject_subtype.subject_type.value,
            "subject_subtype": subject.subject_subtype.value,
            "id": subject.id,
        },
    }

    if coordinates:
        feature["geometry"] = {
            "type": "LineString" if not is_point else "Point",
            "coordinates": coordinates if not is_point else coordinates.tuple,
        }

    properties = feature["properties"]

    # Add optional display name (e.g., parsed manufacturer_id for buoy gear)
    if display_name:
        properties["name"] = display_name

    # Add optional additional properties (e.g., display_id, manufacturer for buoy gear)
    if additional:
        properties["additional"] = additional

    # Add optional device status properties
    if device_status_properties:
        properties["device_status_properties"] = device_status_properties

    if hasattr(subject, "color"):
        # see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties["stroke"] = subject.color
        properties["stroke-opacity"] = 1.0
        properties["stroke-width"] = 2
        properties["image"] = image_url

    for k in (
        "last_voice_call_start_at",
        "location_requested_at",
        "radio_state_at",
        "radio_state",
    ):
        val = getattr(subject, f"status_{k}", None)
        properties[k] = val

    # see https://github.com/mapbox/geojson-coordinate-properties
    if is_point:
        properties["coordinateProperties"] = {"time": time}
        properties["DateTime"] = time  # Left in for backward compatibility.
    else:
        properties["coordinateProperties"] = {"times": coordinate_times or []}

    return feature


class GPXTrackFileUploadSerializer(serializers.Serializer):
    gpx_file = serializers.FileField()

    class Meta:
        fields = ("gpx_file",)

    def validate(self, data):
        file = data.get("gpx_file")
        file_name = file.name
        if not file_name.lower().endswith(".gpx"):
            raise serializers.ValidationError({"data": "Only .gpx files can be imported."})
        return data


DEFAULT_SERIALIZER_MAPPING = {
    "observations.subject": {"serializer": SubjectSerializer, "field": "subject"},
    "accounts.user": {"serializer": UserDisplaySerializer, "field": "user"},
}


class SenderReceiverRelatedField(GenericRelatedField):
    def get_field_mapping(self, label="User"):
        return super().get_field_mapping(label)


class MessageSerializer(BaseSerializer, TimestampMixin):
    from core.serializers import PointValidator

    id = serializers.UUIDField(read_only=True)
    sender = SenderReceiverRelatedField(required=False, allow_null=True)
    receiver = SenderReceiverRelatedField(required=False, allow_null=True)

    device = SourceRelatedField(required=False, allow_null=True)
    message_type = choicefield_serializer(models.MESSAGE_TYPES, default=models.OUTBOX)
    text = text_field(required=False, allow_blank=True, allow_null=True)
    status = choicefield_serializer(models.MESSAGE_STATE_CHOICES, default=models.PENDING)
    device_location = GEOPointField(required=False, allow_null=True, validators=[PointValidator()])
    message_time = DateTimeField(required=False, allow_null=True)
    read = serializers.BooleanField(required=False)
    additional = serializers.JSONField(default=dict, allow_null=True)

    class Meta:
        model = models.Message
        fields = (
            "id",
            "sender_id",
            "receiver_id",
            "device_id",
            "message_type",
            "text",
            "status",
            "device_location",
            "message_time",
            "additional",
        )

    def to_representation(self, instance):
        rep = super(MessageSerializer, self).to_representation(instance)

        request = self.context.get("request")
        query_params = request.query_params
        include_additional = query_params.get("include_additional_data", False)
        if not include_additional:
            del rep["additional"]
        return rep

    def create(self, validated_data):
        return models.Message.objects.create(**validated_data)


class AnnouncementSerializer(BaseSerializer):
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(allow_null=True, required=False, max_length=255)
    description = text_field(
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    additional = serializers.JSONField(default=dict, allow_null=True)
    link = serializers.URLField(allow_null=True, required=False)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        if request:
            rep["read"] = request.user in instance.related_users.all()
        return rep


class ReadAnnouncementSerializer(serializers.Serializer):
    news_ids = serializers.ListField(child=serializers.UUIDField(), required=True)


class TrackLimitSerializer(serializers.Serializer):
    limit = serializers.IntegerField(default=None, required=False)


__all__ = [
    "AnnouncementSerializer",
    "FlattenObservationSerializer",
    "GPXTrackFileUploadSerializer",
    "GroupSerializer",
    "MessageSerializer",
    "ObservationSerializer",
    "ReadAnnouncementSerializer",
    "RecursiveSerializer",
    "RegionSerializer",
    "SourceProviderSerializer",
    "SourceSerializer",
    "SubjectGeoJsonSerializer",
    "SubjectSerializer",
    "SubjectSourceSerializer",
    "SubjectStatusSerializer",
    "SubjectTrackSerializer",
    "TrackLimitSerializer",
    "TrackSerializer",
]
