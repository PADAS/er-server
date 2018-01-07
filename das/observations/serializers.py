from collections import OrderedDict

from django.contrib.gis.geos import Point
import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField
from drf_extra_fields.fields import DateTimeRangeField
from django.db.utils import IntegrityError
from django.core.urlresolvers import reverse

from core.serializers import ContentTypeField

from django.conf import settings
from observations import models
import utils.json
import datetime
from dateutil.parser import parse as parse_date
from utils import add_base_url
from datetime import datetime, timedelta
import pytz
import time
import sys



class RegionSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = models.Region
        fields = ('slug', 'region', 'country')


class RecursiveSerializer(rest_framework.serializers.Serializer):
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(instance, context=self.context)
        return serializer.data


def create_sg_serializer(name, model, serializer):
    contained_field = '{0}s'.format(serializer.Meta.model._meta.model_name)
    meta = type('Meta', (object,), dict(model=model,
                                        fields=('name', 'id', 'subgroups')))
    subgroups = RecursiveSerializer(many=True, read_only=True, source='children')
    return type(name, (GroupSerializer,), dict(serializer=serializer, Meta=meta,
                                               subgroups=subgroups,
                                               contained_field=contained_field))


class GroupSerializer(rest_framework.serializers.ModelSerializer):

    def to_representation(self, instance):
        user = getattr(self.context.get('request', None), 'user', None)
        data_serializer = self.serializer(context=self.context)
        contained_field = self.contained_field

        queryset = getattr(instance, 'get_all_{0}'.format(contained_field))(
            user=user, active=True)

        queryset = queryset.order_by('name')

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
    subject_type = rest_framework.serializers.CharField(max_length=100, required=False)
    subject_subtype = rest_framework.serializers.CharField(max_length=100, required=False)
    additional = rest_framework.serializers.JSONField(label='Additional data', required=False)
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
        fields = ('id', 'name', 'subject_type', 'subject_subtype', 'additional',) + read_only_fields

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
            maximum_allowed_age = None
            minimum_allowed_age = None
            mou_expiry_date = user.additional.get('expiry', None)

            for permission_tuple in sorted(models.Subject.VIEW_BEGIN_WINDOWS, key=lambda _: _[1], reverse=True):
                if user.has_perm(permission_tuple[0]) and (maximum_allowed_age is None or permission_tuple[1] > maximum_allowed_age):
                    maximum_allowed_age = permission_tuple[1]
                    break

            for permission_tuple in sorted(models.Subject.VIEW_END_WINDOWS, key=lambda _: _[1]):
                if user.has_perm(permission_tuple[0]) and (minimum_allowed_age is None or permission_tuple[1] < minimum_allowed_age):
                    minimum_allowed_age = permission_tuple[1]
                    break

            if mou_expiry_date is not None:
                now = pytz.utc.localize(datetime.utcnow())
                mou_expiry_date = pytz.utc.localize(parse_date(mou_expiry_date))
                mou_expiry_age = now - mou_expiry_date

                minimum_allowed_age = max(mou_expiry_age.days, minimum_allowed_age)
                if maximum_allowed_age < minimum_allowed_age:
                    maximum_allowed_age = None
                    minimum_allowed_age = None

            if minimum_allowed_age is not None and maximum_allowed_age is not None:
                start, end = instance.subjectstatus_set.get_range_endpoints(maximum_allowed_age * 24, minimum_allowed_age * 24)
                if start is not None and end is not None:
                    default_window_cutoff = pytz.utc.localize(datetime.utcnow() - timedelta(days=settings.SHOW_TRACK_DAYS))
                    rep['tracks_available'] = end.recorded_at > default_window_cutoff
                    rep['last_position_status'] = end.additional or {}
                    rep['last_position_date'] = end.recorded_at
                    rep['last_position'] = make_feature(self.context['request'],end.location, instance, time=end.recorded_at, image_url=rep['image_url'])
                    rep['tracks_range'] = (start.recorded_at, end.recorded_at)

        if 'request' in self.context:
            request = self.context['request']
            rep['url'] = utils.add_base_url(request, reverse('subject-view',args=[instance.id, ]))
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
        return value.name if value else None

    def to_internal_value(self, data):
        if data:
            try:
                return models.SourceProvider.objects.get(name=data)
            except models.SourceProvider.DoesNotExist:
                raise rest_framework.serializers.ValidationError(
                    {'provider_name': 'Value \'%s\' does not exist.' % data})
        return None

    @property
    def choices(self):
        return OrderedDict(((row.name, row.name)
                            for row in self.get_queryset()))

class SourceSerializer(rest_framework.serializers.Serializer):

    id = rest_framework.serializers.UUIDField(read_only=True)
    source_type = rest_framework.serializers.ChoiceField(allow_null=True, choices=(('tracking-device', 'Tracking Device'), ('trap', 'Trap'), ('seismic', 'Seismic sensor'), ('firms', 'FIRMS data'), ('gps-radio', 'gps radio')), label='Type of data expected', required=False)
    manufacturer_id = rest_framework.serializers.CharField(allow_null=True, label='Device manufacturer id', max_length=100, required=False)
    model_name = rest_framework.serializers.CharField(allow_null=True, label='Device model name', max_length=100, required=False)
    additional = rest_framework.serializers.JSONField(label='Additional data')
    provider = SourceProviderRelatedField()
    subject = rest_framework.serializers.JSONField(label='Subject data', required=False)
    content_type = ContentTypeField(read_only=True)
    created_at = rest_framework.serializers.DateTimeField(read_only=True)
    updated_at = rest_framework.serializers.DateTimeField(read_only=True)

    class Meta:
        model = models.Source
        fields = ('id', 'source_type', 'manufacturer_id', 'model_name', 'additional', 'provider', 'owner')

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

            rep['url'] = utils.add_base_url(request, reverse('source-view', args=[instance.id,]))

        return rep


    def create(self, validated_data):
        if 'request' in self.context:
            request = self.context['request']
            validated_data['owner'] = request.user

        return models.Source.objects.ensure_source(**validated_data)

class SourceProviderSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(read_only=True)
    name = rest_framework.serializers.CharField(label='Source Provider', max_length=100, required=True)
    class Meta:
        model = models.SourceProvider
        fields = ('id', 'name')

    def create(self, validated_data):

        instance, created = models.SourceProvider.objects.get_or_create(**validated_data)
        return instance

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

        if not data: return None

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
        fields = ('id', 'location', 'created_at', 'recorded_at', 'additional', 'source')
        id_field = False
        geo_field = 'location'

    def to_representation(self, instance):
        rep = super(ObservationSerializer, self).to_representation(instance)
        return rep


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
            'subject_type': subject.subject_type,
            'subject_subtype': subject.subject_subtype,
            'id': subject.id,
        },
    }
    properties = feature['properties']
    if hasattr(subject, 'color'):
        #see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties['stroke'] = subject.color
        properties['stroke-opacity'] = 1.0
        properties['stroke-width'] = 2
        properties['image'] = image_url

    #see https://github.com/mapbox/geojson-coordinate-properties
    if coordinate_times:
        properties['coordinateProperties'] = {'times': coordinate_times}
    if time:
        properties['DateTime'] = time
    return feature

