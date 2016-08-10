from django.contrib.gis.geos import Point
import rest_framework.serializers

from core.serializers import ContentTypeField
from observations import models
import utils.json
from utils import add_base_url


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

        rep = super().to_representation(instance)
        data = [data_serializer.to_representation(s)
                for s in queryset]
        rep[contained_field] = data
        return rep


class SubjectSerializer(rest_framework.serializers.ModelSerializer):
    content_type = ContentTypeField()
    additional_fields = ('region', 'country', 'sex',
                         'species',)

    class Meta:
        model = models.Subject
        readonly_fields = ('image_url', 'color')
        fields = ('id', 'name', 'subject_type', 'subject_subtype',
                  'content_type') + readonly_fields

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
                rep['image_url'] = instance.get_last_position_image_url()
            elif user.has_any_perms(model.VIEW_DELAYED_PERMS, instance):
                last_position = instance.subjectstatus_set.get_delayed()

            first_position = None
            if last_position:
                first_position = instance.subjectstatus_set.get_delayed()

                if 'state' in last_position.additional:
                    rep['state'] = last_position.additional['state']

            rep['tracks_available'] = bool(last_position)
            if last_position:
                rep['last_position_date'] = last_position.recorded_at
                rep['last_position'] = make_feature(self.context['request'],
                                                    last_position.location,
                                                    instance,
                                                    time=last_position.recorded_at,
                                                    image_url=rep['image_url'])
                if first_position:
                    rep['tracks_range'] = (first_position.recorded_at,
                                           last_position.recorded_at)
        return rep


class SourceSerializer(rest_framework.serializers.ModelSerializer):

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
        except AttributeError:
            pass
        return rep


class TrackSerializer(rest_framework.serializers.Serializer):

    def to_representation(self, instance):

        if 'subject' in self.context:
            image_url = self.context['subject'].image_url
        else:
            image_url = instance.get_last_position_image_url()
        feature = make_feature(self.context['request'],
                               self.context['coordinates'], instance,
                               self.context['times'], image_url=image_url)
        rep = utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)


        return rep


class ObservationSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = models.Observation
        fields = ('id', 'location', 'created_at', 'recorded_at', 'additional', 'source')
        id_field = False
        geo_field = 'location'


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

