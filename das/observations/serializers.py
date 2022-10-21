import json
import logging
from collections import OrderedDict
from datetime import MAXYEAR, MINYEAR, datetime, timedelta
from typing import NamedTuple

import pytz
from drf_extra_fields.fields import DateTimeRangeField
from drf_extra_fields.geo_fields import PointField
from rest_framework_gis.serializers import GeoFeatureModelListSerializer

import rest_framework
import rest_framework.serializers
from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import jsonb
from django.db.models import Q
from django.urls import reverse
from rest_framework.fields import DateTimeField

import utils.json
from accounts.serializers import UserDisplaySerializer
from core.fields import GEOPointField, choicefield_serializer, text_field
from core.serializers import (BaseSerializer, ContentTypeField,
                              GenericRelatedField, TimestampMixin)
from observations import models
from observations.models import (STATIONARY_SUBJECT_VALUE, SubjectSource,
                                 transform_additional_data)
from observations.utils import (dateparse, get_maximum_allowed_age,
                                get_minimum_allowed_age, get_null_point,
                                is_subject_stationary_subject)
from utils import add_base_url
from utils.json import zeroout_microseconds

logger = logging.getLogger(__name__)


class RegionSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = models.Region
        fields = ('slug', 'region', 'country')


class RecursiveSerializer(rest_framework.serializers.Serializer):
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(
            instance, context=self.context)
        return serializer.data


def create_sg_serializer(name, model, serializer, include_subgroups=True):
    contained_field = '{0}s'.format(serializer.Meta.model._meta.model_name)
    meta_fields = ('name', 'id')
    if include_subgroups:
        meta_fields += ('subgroups',)
    meta = type('Meta', (object,), dict(model=model,
                                        fields=meta_fields))

    gs_fields = dict(serializer=serializer, Meta=meta,
                     contained_field=contained_field)
    if include_subgroups:
        gs_fields["subgroups"] = RecursiveSerializer(
            many=True, read_only=True, source='children')

    return type(name, (GroupSerializer,), gs_fields)


class GroupSerializer(rest_framework.serializers.ModelSerializer):

    def to_representation(self, instance):
        user = getattr(self.context.get('request', None), 'user', None)
        data_serializer = self.serializer(context=self.context)
        contained_field = self.contained_field
        active = True

        params = self.context["request"].GET \
            .get("include_inactive", None)
        try:
            if params and json.loads(params.lower()):
                active = None
        except Exception:
            pass

        mou_date = user.additional.get('expiry', None)
        mou_date = dateparse(mou_date) if mou_date else None

        queryset = getattr(instance, 'get_all_{0}'.format(contained_field))(
            user=user, active=active, include_from_subgroups=False, mou_expiry_date=mou_date)

        # queryset = queryset.order_by('name')
        # queryset variable contains list of sources linked with source group.
        # name is not a field of source object but model_name is.
        # queryset = sorted(queryset, key=lambda k: k.model_name, reverse=False)
        rep = super().to_representation(instance)
        data = [data_serializer.to_representation(s)
                for s in queryset]
        rep[contained_field] = data
        return rep


def get_subject_display(subject):
    return subject.name


class SubjectTypeRelatedField(rest_framework.serializers.RelatedField):

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
                raise rest_framework.serializers.ValidationError(
                    f'subject_type : {data} does not exist')


class SubjectSubTypeRelatedField(rest_framework.serializers.RelatedField):

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
                raise rest_framework.serializers.ValidationError(
                    f'subject_subtype : {data} does not exist')


class CommonNameRelatedField(rest_framework.serializers.RelatedField):

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
                raise rest_framework.serializers.ValidationError(
                    f'common_name : {data} does not exist')


class TimezoneOverflowAwareDateTimeField(DateTimeField):
    def enforce_timezone(self, value):
        """we wont enforce timezone on datetime object with max year number or min year number; to prevent OverFlow"""
        if value.year >= MAXYEAR or value.year <= MINYEAR:
            return value
        else:
            return super().enforce_timezone(value)


class SubjectSourceSerializer(rest_framework.serializers.ModelSerializer):
    assigned_range = DateTimeRangeField(
        child=TimezoneOverflowAwareDateTimeField())
    location = PointField(required=False)

    class Meta:
        model = SubjectSource
        fields = ("id", "assigned_range", "source",
                  "subject", "additional", "location")

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


class SubjectSerializer(rest_framework.serializers.Serializer):

    content_type = ContentTypeField(read_only=True, required=False)

    id = rest_framework.serializers.UUIDField(required=False,)
    name = rest_framework.serializers.CharField(max_length=100)
    subject_type = rest_framework.serializers.CharField(
        max_length=100, required=False, read_only=True)
    subject_subtype = SubjectSubTypeRelatedField()
    common_name = CommonNameRelatedField(required=False)
    additional = rest_framework.serializers.JSONField(
        label='Additional data', required=False)
    created_at = rest_framework.serializers.DateTimeField(read_only=True)
    updated_at = rest_framework.serializers.DateTimeField(read_only=True)
    is_active = rest_framework.serializers.BooleanField(required=False)

    additional_fields = ('region', 'country', 'sex',
                         'species', 'additional')

    allowed_partial_update_fields = (
        "name", "subject_subtype", "common_name", "additional", "is_active")

    class Meta:
        model = models.Subject
        read_only_fields = ('image_url', 'color',
                            'content_type', 'subject_type')
        fields = ('id', 'name', 'subject_subtype', 'common_name',
                  'additional', 'is_active',) + read_only_fields

    def to_internal_value(self, data):
        if 'id' in data:
            return models.Subject.objects.get(id=data['id'])
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        update_fields = []
        for k, v in validated_data.items():
            if k not in self.allowed_partial_update_fields:
                continue
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                update_fields.append(k)
        if update_fields:
            instance.save(update_fields=update_fields)
        return instance

    def to_representation(self, instance):
        user = getattr(self.context.get('request', None), 'user', None)
        render_last_location = self.context.get('render_last_location', True)

        rep = super(SubjectSerializer, self).to_representation(instance)
        additional = instance.additional
        additional = {
            k: additional[k] for k in self.additional_fields if k in additional
        }
        rep.update(additional)
        rep['tracks_available'] = False
        rep['image_url'] = instance.image_url
        is_stationary_subject = self._is_stationary_subject(instance)
        if is_stationary_subject:
            rep["is_static"] = True

        request = self.context.get('request')

        if user and render_last_location:
            # Find the user's allowed viewable date range
            maximum_allowed_age = get_maximum_allowed_age(user)
            minimum_allowed_age = get_minimum_allowed_age(user)
            # additional.get('expiry', None)
            mou_expiry_date = user.mou_expiry_date

            if mou_expiry_date is not None:
                if not mou_expiry_date.tzinfo:
                    mou_expiry_date = mou_expiry_date.replace(tzinfo=pytz.utc)

                mou_expiry_age = datetime.now(
                    tz=pytz.utc) - mou_expiry_date

                minimum_allowed_age = max(
                    mou_expiry_age.days, minimum_allowed_age)
                if maximum_allowed_age < minimum_allowed_age:
                    maximum_allowed_age = None
                    minimum_allowed_age = None

            if minimum_allowed_age is not None and maximum_allowed_age is not None:
                default_window_cutoff = pytz.utc.localize(
                    datetime.utcnow() - timedelta(days=settings.SHOW_TRACK_DAYS))

                statusvalues = resolve_status_values(instance)

                # Get last_position details from latest accessible source
                # according to SourceGroup permissions.
                linked_sources = self.context.get(
                    'subject_linked_sources', {}).get(instance.id)
                if linked_sources:
                    # Fetch latest & oldest Observations available to plot
                    # latest_position & tracks_range.
                    latest_source = linked_sources['latest_source']
                    latest_range = linked_sources['latest_range']
                    linked_sources['oldest_source']
                    oldest_range = linked_sources['oldest_range']

                    if latest_range and oldest_range:
                        query = models.Observation.objects.filter(
                            source=latest_source,
                            recorded_at__range=[
                                latest_range.lower,
                                latest_range.upper
                            ]
                        )
                        latest_observation = query.order_by(
                            '-recorded_at').first()
                        oldest_observation = query.order_by(
                            'recorded_at').first()

                        rep['tracks_available'] = statusvalues.recorded_at and statusvalues.recorded_at > default_window_cutoff
                        if latest_observation and oldest_observation:
                            additional = latest_observation.additional
                            if not isinstance(additional, dict):
                                additional = {}
                            # Construct a response with latest_location
                            # details.
                            rep['tracks_available'] = True
                            rep['last_position_status'] = {
                                'last_voice_call_start_at': additional.get('last_voice_call_start_at'),
                                'radio_state_at': additional.get('radio_state_at'),
                                'radio_state': additional.get('radio_state'),
                            }
                            rep['last_position_date'] = latest_observation.recorded_at

                            location = latest_observation.location
                            if is_stationary_subject and instance.subjectsources.last().location:
                                location = instance.subjectsources.last().location

                            rep['last_position'] = make_feature(
                                request,
                                location,
                                instance,
                                time=latest_observation.recorded_at,
                                image_url=rep['image_url'])
                else:
                    # If no linked_sources are available then fetch
                    # latest_position from SubjectStatus as usual.

                    if mou_expiry_date and (mou_expiry_date.replace(tzinfo=pytz.utc) <= datetime.now(tz=pytz.utc)) and request.method == 'GET':
                        observation = get_observation_location(
                            instance, mou_expiry_date, default_window_cutoff)
                        location = observation.location if observation else get_null_point()
                        recorded_at = observation.recorded_at if observation else None
                    else:
                        location = statusvalues.location if statusvalues.location else get_null_point()
                        recorded_at = statusvalues.recorded_at

                    tracks_available = recorded_at and recorded_at > default_window_cutoff
                    rep['tracks_available'] = tracks_available
                    rep['last_position_status'] = {
                        'last_voice_call_start_at':  None if statusvalues.last_voice_call_start_at == models.DEFAULT_STATUS_VALUE_DATE else statusvalues.last_voice_call_start_at,
                        'radio_state_at': None if statusvalues.radio_state_at == models.DEFAULT_STATUS_VALUE_DATE else statusvalues.radio_state_at,
                        'radio_state': statusvalues.radio_state
                    }
                    if is_stationary_subject and instance.subjectsources.last().location:
                        location = instance.subjectsources.last().location

                    if tracks_available:
                        rep['last_position_date'] = recorded_at
                        rep['last_position'] = make_feature(
                            request,
                            location,
                            instance,
                            time=recorded_at, image_url=rep['image_url']
                        )

                rep['device_status_properties'] = self._get_device_status_properties(
                    statusvalues)
                if is_stationary_subject:
                    rep['device_status_properties'] = self._get_device_properties_static_sensor(
                        statusvalues, instance)
                    rep["tracks_available"] = False

        if request:
            rep['url'] = utils.add_base_url(
                request, reverse('subject-view', args=[instance.id, ]))

            message_content = []

            # for ss in get_subjectsources_with_2way_msg(instance):
            if "two_way_subject_sources" in self.context.keys():
                # two_way_subject_sources is a dict by source_id
                two_way_subject_sources = self.context["two_way_subject_sources"]
                instance_id = instance.id
                for subject_source in [ss_for_subject
                                       for ss_by_source in two_way_subject_sources.values()
                                       for ss_for_subject in ss_by_source.values()
                                       if ss_for_subject['subject_id'] == instance_id]:
                    message_url = utils.add_base_url(
                        request, reverse('messages-view'))
                    data = {
                        "source_provider": subject_source["source__provider__display_name"],
                        "url": f"{message_url}?subject_id={str(instance.id)}&source_id={str(subject_source['source_id'])}"
                    }
                    message_content.append(data)

            if message_content:
                rep["messaging"] = message_content

        if self.context.get('tracks', False):
            track_serializer = SubjectTrackSerializer(
                instance, context=self.context)
            rep['tracks'] = track_serializer.data

        return rep

    def create(self, validated_data):
        if 'request' in self.context:
            request = self.context['request']
            validated_data['owner'] = request.user

        return models.Subject.objects.create_subject(**validated_data)

    def _is_stationary_subject(self, instance):
        if (
                instance.subject_subtype.subject_type.value == STATIONARY_SUBJECT_VALUE
                and instance.subjectsources.last()
        ):
            return True
        return False

    def _get_device_status_properties(self, status_values):
        if hasattr(status_values, 'device_status_properties'):
            return status_values.device_status_properties
        return None

    def _get_device_properties_static_sensor(self, status_values, subject):
        device_status_properties = self._get_device_status_properties(
            status_values)
        default_measure = self._get_default_measure(subject)
        if device_status_properties:
            for device in device_status_properties:
                device["default"] = False
                if device.get("label") == default_measure:
                    device["default"] = True
        return device_status_properties

    def _get_default_measure(self, subject):
        last_subject_source = subject.subjectsources.last()
        if last_subject_source:
            transforms = last_subject_source.source.provider.transforms
            if transforms:
                for transform in transforms:
                    if transform.get("default"):
                        return transform.get("label")
        return ""


def get_subjectsources_with_2way_msg(subject):
    """filter based on messaging capabilities that are attached to either source or source-provider
    link to truth table. https://vulcan.atlassian.net/browse/DAS-6713?focusedCommentId=70634
    """
    condition = (Q(two_way_messaging=True) &
                 (Q(source_two_way_messaging=False, source_two_way_messaging__isnull=False)))

    subject_sources = models.SubjectSource.objects.filter(subject=subject).annotate(
        two_way_messaging=jsonb.KeyTransform(
            'two_way_messaging', 'source__provider__additional'),
        source_two_way_messaging=jsonb.KeyTransform('two_way_messaging', 'source__additional')).exclude(
        Q(two_way_messaging__isnull=True) | Q(two_way_messaging=False) | condition)
    return subject_sources


class SubjectGeoJsonSerializer(SubjectSerializer):
    @classmethod
    def many_init(cls, *args, **kwargs):
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {'child': child_serializer}
        list_kwargs.update(dict([
            (key, value) for key, value in kwargs.items()
            if key in rest_framework.serializers.LIST_SERIALIZER_KWARGS
        ]))
        meta = getattr(cls, 'Meta', None)
        list_serializer_class = getattr(
            meta, 'list_serializer_class', GeoFeatureModelListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    def create(self, validated_data):
        raise NotImplemented('Create subject using GeoJson not supported')

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        subject = rep.get('last_position', None)
        if not subject:
            subject = make_feature(
                self.context['request'], None, instance,
                time=None, image_url=rep['image_url']
            )
        return subject


class SubjectStatusValues(NamedTuple):
    recorded_at: datetime
    location: Point
    radio_state: str
    radio_state_at: datetime
    last_voice_call_start_at: datetime
    device_status_properties: dict


def resolve_status_values(subject):
    '''
    Parse subject-status values from
    :param subject:
    :return:
    '''
    if hasattr(subject, 'status_radio_state'):
        return SubjectStatusValues(**dict((k, getattr(subject, f'status_{k}', None)) for k in SubjectStatusValues._fields))
    try:
        return models.SubjectStatus.objects.get_current_status(subject)
    except models.SubjectStatus.DoesNotExist:
        raise ValueError(
            f'SubjectStatus does not exist for subject ID: {subject.id}')


def get_observation_location(subject, mou_date, default_window_cutoff):
    """Return the latest subject observation less than the date of expiry,
    and more recent than the site window cutoff

    Args:
        subject ([Subject]): observation subject
        mou_date ([datetime]): user mou expiry
        default_window_cutoff ([datetime]): the since value
    Returns:
        [Observation]: the observation
    """
    if mou_date < default_window_cutoff:
        return None
    observation = models.Observation.objects.get_subject_observations(
        subject, since=default_window_cutoff,  until=mou_date, order_by='-recorded_at'
    ).first()

    return observation


class SourceProviderRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return models.SourceProvider.objects.all()

    def to_representation(self, value):
        return value.provider_key if value else None

    def to_internal_value(self, data):
        if data:
            try:
                return models.SourceProvider.objects.get(provider_key=data)
            except models.SourceProvider.DoesNotExist:
                raise rest_framework.serializers.ValidationError(
                    {'provider_key': 'Value \'%s\' does not exist.' % data})
        return None

    @property
    def choices(self):
        return OrderedDict(((row.provider_key, row.display_name)
                            for row in self.get_queryset()))


class SourceSerializer(rest_framework.serializers.Serializer):

    id = rest_framework.serializers.UUIDField(read_only=True)
    source_type = rest_framework.serializers.ChoiceField(allow_null=True, choices=(('tracking-device', 'Tracking Device'), ('trap', 'Trap'), (
        'seismic', 'Seismic sensor'), ('firms', 'FIRMS data'), ('gps-radio', 'gps radio')), label='Type of data expected', required=False)
    manufacturer_id = rest_framework.serializers.CharField(
        allow_null=True, label='Device manufacturer id', max_length=100, required=False)
    model_name = rest_framework.serializers.CharField(
        allow_null=True, label='Device model name', max_length=100, required=False)
    additional = rest_framework.serializers.JSONField(label='Additional data')
    provider = SourceProviderRelatedField()
    subject = rest_framework.serializers.JSONField(
        label='Subject data', required=False)
    content_type = ContentTypeField(read_only=True)
    created_at = rest_framework.serializers.DateTimeField(read_only=True)
    updated_at = rest_framework.serializers.DateTimeField(read_only=True)

    class Meta:
        model = models.Source
        fields = ('id', 'source_type', 'manufacturer_id',
                  'model_name', 'additional', 'provider', 'owner')

    def to_representation(self, instance):
        rep = super(SourceSerializer, self).to_representation(instance)
        rep.update(instance.additional)
        try:
            subject_sources = self.context['view'].two_way_subject_sources
            subject_source = subject_sources.get(source=instance)
            rep['assigned_range'] = subject_source.assigned_range
        except (AttributeError, KeyError):
            pass

        if 'request' in self.context:
            request = self.context['request']

            rep['url'] = utils.add_base_url(
                request, reverse('source-view', args=[instance.id, ]))

        return rep

    def create(self, validated_data):
        if 'request' in self.context:
            request = self.context['request']
            validated_data['owner'] = request.user

        source, created = models.Source.objects.get_source(**validated_data)
        return source


class SourceProviderSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(read_only=True)
    provider_key = rest_framework.serializers.CharField(
        label='Source Provider Value', max_length=100, required=True)
    display_name = rest_framework.serializers.CharField(
        label='Display Name', max_length=100,)
    additional = rest_framework.serializers.JSONField(
        label='Additional Data', )

    class Meta:
        model = models.SourceProvider
        fields = ('id', 'provider_key', 'display_name', 'additional')

    def create(self, validated_data):
        instance = models.SourceProvider.objects.create_provider(
            **validated_data)
        return instance

    def update(self, instance, validated_data):
        instance.provider_key = validated_data.get(
            "provider_key", instance.provider_key)
        instance.display_name = validated_data.get(
            "display_name", instance.display_name)
        instance.additional = validated_data.get(
            "additional", instance.additional)
        instance.save()
        return instance


class SubjectTrackSerializer(rest_framework.serializers.BaseSerializer):
    def to_representation(self, subject):
        image_url = subject.image_url
        user = self.context['request'].user
        tracks_since = self.context.get('tracks_since', None)
        tracks_until = self.context.get('tracks_until', None)
        tracks_limit = self.context.get('tracks_limit', None)

        subject_linked_sources = self.context.get(
            'subject_linked_sources', None)

        if subject_linked_sources:
            coordinates = []
            times = []
            EMPTY_POINT = Point(0, 0)
            # Fetch Observations only from the linked sources to limit view
            # on a Source level
            for source in subject_linked_sources:
                subject_source = models.SubjectSource.objects.get(
                    source=source,
                    subject=subject
                )

                lower = subject_source.safe_assigned_range.lower
                upper = subject_source.safe_assigned_range.upper

                queryset = models.Observation.objects.get_subjectsource_observations(
                    subject_source,
                    since=lower,
                    until=upper,
                )
                queryset = queryset.exclude(location=EMPTY_POINT)
                queryset = queryset.values("location", "recorded_at")
                for observation in list(queryset):
                    coordinates.append(observation["location"].coords)
                    times.append(zeroout_microseconds(
                        observation["recorded_at"]))
        else:
            coordinates, times = subject.get_track(
                user,
                tracks_since,
                tracks_until,
                tracks_limit
            )

        feature = make_feature(
            self.context['request'],
            coordinates,
            subject,
            times,
            image_url=image_url
        )

        rep = utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)

        return rep


class SubjectStatusSerializer(rest_framework.serializers.BaseSerializer):
    def to_representation(self, subject_status):
        coordinates = Point(x=subject_status.location.x,
                            y=subject_status.location.y, srid=4326)

        feature = make_subjectstatus_feature(self.context['request'],
                                             coordinates,
                                             subject_status)

        feature['device_status_properties'] = subject_status.additional.get(
            'device_status_properties')

        return feature


class TrackSerializer(rest_framework.serializers.Serializer):

    def to_representation(self, instance):

        # TODO: Review with Shawn, wrt to recent changes in SubjectTracksView.
        image_url = (self.context.get('subject') or instance).image_url

        feature = make_feature(self.context['request'],
                               self.context['coordinates'], instance,
                               self.context['times'], image_url=image_url)
        rep = utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)

        return rep


class SourceRelatedField(rest_framework.serializers.RelatedField):
    def get_queryset(self):
        return models.Source.objects.select_related('provider').all()

    def to_representation(self, source):
        '''
        :param source:
        :return: dict representation of this related source.
        '''
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


class ObservationSerializer(rest_framework.serializers.ModelSerializer):
    source = rest_framework.serializers.UUIDField(source='source_id')
    location = PointField(required=False)

    class Meta:
        model = models.Observation
        fields = ('id', 'location', 'created_at',
                  'recorded_at', 'additional', 'source')
        id_field = False
        geo_field = 'location'

    def to_representation(self, instance):
        rep = super(ObservationSerializer, self).to_representation(instance)
        self.dict_to_representation(rep, self.context)
        return rep

    @staticmethod
    def dict_to_representation(rep, params):
        # Since the queryset returns a dict, modify it here
        if not rep.get("source"):
            # changing source_id to source
            rep["source"] = rep.pop("source_id")

        if rep.get("source_transforms") and rep.get("additional"):
            rep["device_status_properties"] = transform_additional_data(
                rep["additional"], rep["source_transforms"])

        if params.get('include_details'):
            # and adding observation details if requested.
            rep['observation_details'] = rep['additional']

        location = rep.get("location")
        if location and not isinstance(location, dict):
            rep["location"] = dict(longitude=location.x, latitude=location.y)

        rep.pop('additional', None)
        rep.pop('source_transforms', None)
        return rep


class FlattenObservationSerializer(rest_framework.serializers.ModelSerializer):
    location = PointField(required=False)

    class Meta:
        model = models.Observation
        fields = ('location', 'recorded_at')

    def to_representation(self, instance):
        rep = super(FlattenObservationSerializer,
                    self).to_representation(instance)

        # TODO: Figure out why coordinates are coming as strings.
        x = float(rep['location']['longitude'])
        y = float(rep['location']['latitude'])

        representation = {'coordinates': [x, y],
                          'time': rep.get('recorded_at')}
        return representation


SUBJECT_STATUS_RETURN_FIELDS = (
    'last_voice_call_start_at', 'location_requested_at', 'radio_state_at') + ('radio_state',)


def make_subjectstatus_feature(request, location: Point, subjectstatus):

    image_url = add_base_url(request, subjectstatus.subject.image_url)

    feature = {
        'geometry': {
            'type': 'Point',
            'coordinates': location.tuple
        },
        'type': 'Feature',
        'properties': {
            'id': subjectstatus.subject_id,
            'name': subjectstatus.subject.name,
            'type': subjectstatus.subject.subject_subtype.subject_type.value,
            'subtype': subjectstatus.subject.subject_subtype.value,
            'image': image_url,
            'state': subjectstatus.radio_state,
            'coordinateProperties': {
                'time': subjectstatus.recorded_at
            }
        }

    }

    for k in ('last_voice_call_start_at', 'location_requested_at', 'radio_state_at'):
        val = getattr(subjectstatus, k, None)
        if val:
            feature['properties'][k] = val

    return feature


def make_feature(request, coordinates, subject, coordinate_times=None, time=None, image_url=None):
    is_point = isinstance(coordinates, Point)
    image_url = add_base_url(request, image_url or subject.image_url)
    feature = {
        'type': 'Feature',
        'geometry': None,
        'properties': {
            'title': subject.name,
            'subject_type': subject.subject_subtype.subject_type.value,
            'subject_subtype': subject.subject_subtype.value,
            'id': subject.id,
        },
    }

    if coordinates:
        feature['geometry'] = {
            'type': 'LineString' if not is_point else 'Point',
            'coordinates': coordinates if not is_point else coordinates.tuple
        }

    properties = feature['properties']
    if hasattr(subject, 'color'):
        # see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties['stroke'] = subject.color
        properties['stroke-opacity'] = 1.0
        properties['stroke-width'] = 2
        properties['image'] = image_url

    for k in ('last_voice_call_start_at', 'location_requested_at', 'radio_state_at', 'radio_state',):
        val = getattr(subject, f'status_{k}', None)
        properties[k] = val

    # see https://github.com/mapbox/geojson-coordinate-properties
    if is_point:
        properties['coordinateProperties'] = {'time': time}
        properties['DateTime'] = time  # Left in for backward compatibility.
    else:
        properties['coordinateProperties'] = {'times': coordinate_times or []}

    return feature


class GPXTrackFileUploadSerializer(rest_framework.serializers.Serializer):
    gpx_file = rest_framework.serializers.FileField()

    class Meta:
        fields = ('gpx_file',)

    def validate(self, data):
        file = data.get('gpx_file')
        file_name = file.name
        if not file_name.lower().endswith('.gpx'):
            raise rest_framework.serializers.ValidationError(
                {'data': 'Only .gpx files can be imported.'})
        return data


DEFAULT_SERIALIZER_MAPPING = {
    'observations.subject': {'serializer': SubjectSerializer,
                             'field': 'subject'},
    'accounts.user': {'serializer': UserDisplaySerializer,
                      'field': 'user'}
}


class SenderReceiverRelatedField(GenericRelatedField):
    def get_field_mapping(self, label="User"):
        return super().get_field_mapping(label)


class MessageSerializer(BaseSerializer, TimestampMixin):
    from core.serializers import PointValidator

    id = rest_framework.serializers.UUIDField(read_only=True)
    sender = SenderReceiverRelatedField(required=False, allow_null=True)
    receiver = SenderReceiverRelatedField(required=False, allow_null=True)

    device = SourceRelatedField(required=False, allow_null=True)
    message_type = choicefield_serializer(
        models.MESSAGE_TYPES, default=models.OUTBOX)
    text = text_field(required=False, allow_blank=True, allow_null=True)
    status = choicefield_serializer(
        models.MESSAGE_STATE_CHOICES, default=models.PENDING)
    device_location = GEOPointField(
        required=False, allow_null=True, validators=[PointValidator()])
    message_time = DateTimeField(required=False, allow_null=True)
    read = rest_framework.serializers.BooleanField(required=False)
    additional = rest_framework.serializers.JSONField(
        default=dict, allow_null=True)

    class Meta:
        model = models.Message
        fields = ('id', 'sender_id', 'receiver_id', 'device_id', 'message_type', 'text', 'status',
                  'device_location', 'message_time', 'additional')

    def to_representation(self, instance):
        rep = super(MessageSerializer, self).to_representation(instance)

        request = self.context.get('request')
        query_params = request.query_params
        include_additional = query_params.get('include_additional_data', False)
        if not include_additional:
            del rep['additional']
        return rep

    def create(self, validated_data):
        return models.Message.objects.create(**validated_data)


class AnnouncementSerializer(BaseSerializer):
    id = rest_framework.serializers.UUIDField(read_only=True)
    title = rest_framework.serializers.CharField(
        allow_null=True,  required=False, max_length=255)
    description = text_field(
        allow_null=True, allow_blank=True, required=False,)
    additional = rest_framework.serializers.JSONField(
        default=dict, allow_null=True)
    link = rest_framework.serializers.URLField(
        allow_null=True,  required=False)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        if request:
            rep['read'] = request.user in instance.related_users.all()
        return rep


class ReadAnnouncementSerializer(rest_framework.serializers.Serializer):
    news_ids = rest_framework.serializers.ListField(
        child=rest_framework.serializers.UUIDField(), required=True)


class TrackLimitSerializer(rest_framework.serializers.Serializer):
    limit = rest_framework.serializers.IntegerField(
        default=None, required=False)
