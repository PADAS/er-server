import json
from datetime import datetime, timedelta
from collections import OrderedDict
from typing import NamedTuple

import pytz
from dateutil.parser import parse as parse_date
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.conf import settings
import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField
from drf_extra_fields.fields import DateTimeRangeField
from rest_framework_gis.serializers import GeoFeatureModelListSerializer

from core.serializers import ContentTypeField
from observations import models
from observations.utils import get_maximum_allowed_age, get_minimum_allowed_age
import utils.json
from utils.json import zeroout_microseconds
from utils import add_base_url


class RegionSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = models.Region
        fields = ('slug', 'region', 'country')


class RecursiveSerializer(rest_framework.serializers.Serializer):
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(
            instance, context=self.context)
        return serializer.data


def create_sg_serializer(name, model, serializer):
    contained_field = '{0}s'.format(serializer.Meta.model._meta.model_name)
    meta = type('Meta', (object,), dict(model=model,
                                        fields=('name', 'id', 'subgroups')))
    subgroups = RecursiveSerializer(
        many=True, read_only=True, source='children')
    return type(name, (GroupSerializer,), dict(serializer=serializer, Meta=meta,
                                               subgroups=subgroups,
                                               contained_field=contained_field))


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

        queryset = getattr(instance, 'get_all_{0}'.format(contained_field))(
            user=user, active=active, include_from_subgroups=False)

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


class SubjectSourceSerializer(rest_framework.serializers.ModelSerializer):

    assigned_range = DateTimeRangeField()

    class Meta:
        model = models.SubjectSource
        fields = ('id', 'assigned_range', 'soruce', 'subject',
                  'additional')

    def create(self, validated_data):
        return models.SubjectSource.objects.ensure(subject=validated_data['subject'],
                                                   source=validated_data['source'],
                                                   assigned_range=validated_data['assigned_range'])


class SubjectSerializer(rest_framework.serializers.Serializer):

    content_type = ContentTypeField(read_only=True)

    id = rest_framework.serializers.UUIDField(required=False,)
    name = rest_framework.serializers.CharField(max_length=100)
    subject_type = rest_framework.serializers.CharField(
        max_length=100, required=False)
    subject_subtype = rest_framework.serializers.CharField(
        max_length=100, required=False)
    additional = rest_framework.serializers.JSONField(
        label='Additional data', required=False)
    created_at = rest_framework.serializers.DateTimeField(read_only=True)
    updated_at = rest_framework.serializers.DateTimeField(read_only=True)
    is_active = rest_framework.serializers.BooleanField(required=False)

    additional_fields = ('region', 'country', 'sex',
                         'species', 'additional')

    class Meta:
        model = models.Subject
        read_only_fields = ('image_url', 'color', 'content_type')
        fields = ('id', 'name', 'subject_type', 'subject_subtype',
                  'additional','is_active',) + read_only_fields

    def to_internal_value(self, data):
        if 'id' in data:
            return models.Subject.objects.get(id=data['id'])
        return super().to_internal_value(data)

    def to_representation(self, instance):
        user = getattr(self.context.get('request', None), 'user', None)
        render_last_location = self.context.get('render_last_location', True)
        model = self.Meta.model

        rep = super(SubjectSerializer, self).to_representation(instance)
        additional = instance.additional
        additional = {k: additional[k] for k in self.additional_fields
                      if k in additional}
        rep.update(additional)
        rep['tracks_available'] = False
        rep['image_url'] = instance.image_url

        if user and render_last_location:
            # Find the user's allowed viewable date range
            maximum_allowed_age = get_maximum_allowed_age(user)
            minimum_allowed_age = get_minimum_allowed_age(user)
            # additional.get('expiry', None)
            mou_expiry_date = user.mou_expiry_date

            if mou_expiry_date is not None:
                mou_expiry_age = datetime.now(tz=pytz.utc) - mou_expiry_date

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
                    latest_subject_source = linked_sources['latest_subjectsource']
                    oldest_subject_source = linked_sources['oldest_subjectsource']
                    if latest_subject_source and oldest_subject_source:
                        latest_observation = models.Observation.objects.filter(
                            source__subjectsource=latest_subject_source,
                            recorded_at__range=[
                                latest_subject_source.safe_assigned_range.lower,
                                latest_subject_source.safe_assigned_range.upper
                            ]).order_by('-recorded_at').first()

                        oldest_observation = models.Observation.objects.filter(
                            source__subjectsource=oldest_subject_source,
                            recorded_at__range=[
                                oldest_subject_source.safe_assigned_range.lower,
                                oldest_subject_source.safe_assigned_range.upper
                            ]).order_by('recorded_at').first()

                        rep[
                            'tracks_available'] = statusvalues.recorded_at and statusvalues.recorded_at > default_window_cutoff
                        if latest_observation and oldest_observation:
                            additional = latest_observation.additional
                            if not isinstance(additional, dict):
                                additional = {}
                            # Construct a response with latest_location
                            # details.
                            rep['tracks_available'] = True
                            rep['last_position_status'] = {
                                'last_voice_call_start_at': additional.get(
                                    'last_voice_call_start_at'),
                                'radio_state_at': additional.get(
                                    'radio_state_at'),
                                'radio_state': additional.get('radio_state'),
                            }
                            rep['last_position_date'] = \
                                latest_observation.recorded_at
                            rep['last_position'] = make_feature(
                                self.context['request'],
                                latest_observation.location, instance,
                                time=latest_observation.recorded_at,
                                image_url=rep['image_url'])
                else:
                    # If no linked_sources are available then fetch
                    # latest_position from SubjectStatus as usual.

                    rep['tracks_available'] = statusvalues.recorded_at and statusvalues.recorded_at > default_window_cutoff

                    # TODO: These values might be more appropriate in the
                    # geeojson properties.
                    rep['last_position_status'] = {
                        'last_voice_call_start_at': statusvalues.last_voice_call_start_at,
                        'radio_state_at': statusvalues.radio_state_at,
                        'radio_state': statusvalues.radio_state
                    }

                    rep['last_position_date'] = statusvalues.recorded_at
                    rep['last_position'] = make_feature(
                        self.context['request'], statusvalues.location, instance,
                        time=statusvalues.recorded_at, image_url=rep['image_url']
                    )

        if 'request' in self.context:
            request = self.context['request']
            rep['url'] = utils.add_base_url(
                request, reverse('subject-view', args=[instance.id, ]))

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
            subject_sources = self.context['view'].subject_sources
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

        return models.Source.objects.ensure_source(**validated_data)


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

        instance, created = models.SourceProvider.objects.get_or_create(
            **validated_data)
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
                    subject=subject)
                lower = subject_source.safe_assigned_range.lower
                upper = subject_source.safe_assigned_range.upper
                queryset = models.Observation.objects.filter(
                    source__subjectsource__subject=subject,
                    source__subjectsource__source=source,
                    recorded_at__range=[lower, upper])
                queryset = queryset.exclude(location=EMPTY_POINT)
                # queryset = list(queryset)
                for observation in queryset:
                    coordinates.append(observation.location.coords)
                    times.append(zeroout_microseconds(
                        observation.recorded_at))
        else:
            coordinates, times = subject.get_track(
                user, tracks_since, tracks_until, tracks_limit)

        feature = make_feature(self.context['request'],
                               coordinates, subject,
                               times, image_url=image_url)

        rep = utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)

        return rep


class SubjectStatusSerializer(rest_framework.serializers.BaseSerializer):
    def to_representation(self, subject_status):

        image_url = subject_status.subject.image_url
        user = self.context['request'].user

        coordinates = Point(x=subject_status.location.x,
                            y=subject_status.location.y, srid=4326)

        feature = make_subjectstatus_feature(self.context['request'],
                                             coordinates,
                                             subject_status)
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
        return models.Source.objects.all()

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

    location = PointField(required=False)
    source = SourceRelatedField()

    class Meta:
        model = models.Observation
        fields = ('id', 'location', 'created_at',
                  'recorded_at', 'additional', 'source')
        id_field = False
        geo_field = 'location'

    def to_representation(self, instance):
        rep = super(ObservationSerializer, self).to_representation(instance)
        return rep


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
