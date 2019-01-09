from datetime import datetime, timedelta
from collections import OrderedDict

import pytz
from dateutil.parser import parse as parse_date
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.conf import settings
import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField
from drf_extra_fields.fields import DateTimeRangeField

from core.serializers import ContentTypeField
from observations import models
from observations.utils import get_maximum_allowed_age, get_minimum_allowed_age
import utils.json
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

        queryset = getattr(instance, 'get_all_{0}'.format(contained_field))(
            user=user, active=True, include_from_subgroups=False)

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

    additional_fields = ('region', 'country', 'sex',
                         'species', 'additional')

    def create(self, validated_data):

        if 'request' in self.context:
            request = self.context['request']
            validated_data['owner'] = request.user

        return models.Subject.objects.create_subject(**validated_data)

    class Meta:
        model = models.Subject
        read_only_fields = ('image_url', 'color', 'content_type')
        fields = ('id', 'name', 'subject_type', 'subject_subtype',
                  'additional',) + read_only_fields

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
            mou_expiry_date = user.additional.get('expiry', None)

            if mou_expiry_date is not None:
                now = pytz.utc.localize(datetime.utcnow())
                mou_expiry_date = parse_date(mou_expiry_date)
                if not mou_expiry_date.tzinfo:
                    mou_expiry_date = pytz.utc.localize(mou_expiry_date)
                mou_expiry_age = now - mou_expiry_date

                minimum_allowed_age = max(
                    mou_expiry_age.days, minimum_allowed_age)
                if maximum_allowed_age < minimum_allowed_age:
                    maximum_allowed_age = None
                    minimum_allowed_age = None

            if minimum_allowed_age is not None and maximum_allowed_age is not None:
                start, end = instance.subjectstatus_set.get_range_endpoints(
                    maximum_allowed_age * 24, minimum_allowed_age * 24)
                if start is not None and end is not None:
                    default_window_cutoff = pytz.utc.localize(
                        datetime.utcnow() - timedelta(days=settings.SHOW_TRACK_DAYS))
                    rep['tracks_available'] = end.recorded_at > default_window_cutoff

                    # TODO: These values might be more appropriate in the
                    # geeojson properties.
                    rep['last_position_status'] = {
                        'last_voice_call_start_at': end.last_voice_call_start_at,
                        'radio_state_at': end.radio_state_at,
                        'radio_state': end.radio_state
                    }

                    rep['last_position_date'] = end.recorded_at
                    rep['last_position'] = make_feature(
                        self.context['request'], end.location, instance, time=end.recorded_at, image_url=rep['image_url'])
                    rep['tracks_range'] = (start.recorded_at, end.recorded_at)

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
        'geometry': {
            'type': 'LineString' if not is_point else 'Point',
            'coordinates': coordinates if not is_point else coordinates.tuple
        },
        'type': 'Feature',
        'properties': {
            'title': subject.name,
            'subject_type': subject.subject_subtype.subject_type.value,
            'subject_subtype': subject.subject_subtype.value,
            'id': subject.id,
        },
    }
    properties = feature['properties']
    if hasattr(subject, 'color'):
        # see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties['stroke'] = subject.color
        properties['stroke-opacity'] = 1.0
        properties['stroke-width'] = 2
        properties['image'] = image_url

    for ss in subject.subjectstatus_set.filter(delay_hours=0).values(*SUBJECT_STATUS_RETURN_FIELDS):

        properties['subject_state'] = ss.get('radio_state', 'na')

        for k in ('last_voice_call_start_at', 'location_requested_at', 'radio_state_at'):
            val = ss.get(k)
            if val:
                properties[k] = val
        break

    # see https://github.com/mapbox/geojson-coordinate-properties

    if is_point:
        properties['coordinateProperties'] = {'time': time}
        properties['DateTime'] = time # Left in for backward compatibility.
    else:
        properties['coordinateProperties'] = {'times': coordinate_times or []}

    return feature

