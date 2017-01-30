from django.contrib.gis.geos import Point
import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField

from django.core.urlresolvers import reverse

from core.serializers import ContentTypeField
from observations import models
import utils.json
from utils import add_base_url
from datetime import datetime
import pytz

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
        contained_field= self.contained_field

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
    class Meta:
        model = models.SubjectSource

    def create(self, validated_data):
        return models.SubjectSource(**validated_data)

from django.db.utils import IntegrityError
class SubjectSerializer(rest_framework.serializers.Serializer):
    # content_type = ContentTypeField()

    id = rest_framework.serializers.UUIDField(required=False,)
    name = rest_framework.serializers.CharField(max_length=100)
    subject_type = rest_framework.serializers.CharField(max_length=100, required=False)
    subject_subtype = rest_framework.serializers.CharField(max_length=100, required=False)
    additional = rest_framework.serializers.JSONField(label='Additional data', required=False)

    additional_fields = ('region', 'country', 'sex',
                         'species', 'additional')



    def create(self, validated_data):
        return models.Subject.objects.create_subject(**validated_data)

    class Meta:
        model = models.Subject
        readonly_fields = ('image_url', 'color', )
        fields = ('id', 'name', 'subject_type', 'subject_subtype', 'additional',) + readonly_fields

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
        if user and render_last_location:
            last_position = None
            if user.has_any_perms(model.VIEW_POSITION_PERMS, instance):
                last_position = instance.subjectstatus_set.get_last()
                rep['image_url'] = instance.image_url
            elif user.has_any_perms(model.VIEW_DELAYED_PERMS, instance):
                last_position = instance.subjectstatus_set.get_delayed()

            first_position = None
            if last_position:
                first_position = instance.subjectstatus_set.get_delayed()

                if 'state' in last_position.additional:
                    rep['state'] = last_position.additional['state']

            rep['tracks_available'] = bool(last_position)
            if last_position:
                rep['last_position_status'] = last_position.additional or {}
                rep['last_position_date'] = last_position.recorded_at
                rep['last_position'] = make_feature(self.context['request'],
                                                    last_position.location,
                                                    instance,
                                                    time=last_position.recorded_at,
                                                    image_url=rep['image_url'])
                if first_position:
                    rep['tracks_range'] = (first_position.recorded_at,
                                           last_position.recorded_at)
        if 'request' in self.context:
            request = self.context['request']

            rep['url'] = utils.add_base_url(request, reverse('subject-view', args=[instance.id,]))

        return rep


    def create(self, validated_data):
        return models.Subject.objects.create_subject(**validated_data)


class SourceSerializer(rest_framework.serializers.Serializer):
    id = rest_framework.serializers.UUIDField(read_only=True)
    source_type = rest_framework.serializers.ChoiceField(allow_null=True, choices=(('tracking-device', 'Tracking Device'), ('trap', 'Trap'), ('seismic', 'Seismic sensor'), ('firms', 'FIRMS data'), ('gps-radio', 'gps radio')), label='Type of data expected', required=False)
    manufacturer_id = rest_framework.serializers.CharField(allow_null=True, label='Device manufacturer id', max_length=100, required=False)
    model_name = rest_framework.serializers.CharField(allow_null=True, label='Device model name', max_length=100, required=False)
    additional = rest_framework.serializers.JSONField(label='Additional data')

    subject = rest_framework.serializers.JSONField(label='Subject data', required=False)

    class Meta:
        model = models.Source
        fields = ('id', 'source_type', 'manufacturer_id', 'model_name', 'additional')

    def to_representation(self, instance):
        rep = super(SourceSerializer, self).to_representation(instance)
        rep.update(instance.additional)
        try:
            subject_sources = self.context['view'].subject_sources
            subject_source = subject_sources.get(source=instance)
            rep['assigned_range'] = subject_source.assigned_range
        except (AttributeError, KeyError):
            pass
        return rep


    def create(self, validated_data):
        return models.Source.objects.create_source(**validated_data)


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

