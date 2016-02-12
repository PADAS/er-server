from django.contrib.gis.geos import Point
from django.contrib.auth import get_user_model
import rest_framework.serializers


from observations import models
import das_utils.json
from das_utils import add_base_url

class VersionSerializer(rest_framework.serializers.Serializer):
    version = rest_framework.serializers.CharField(read_only=True)


class UserSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        read_only_fields = ('is_staff', 'is_superuser',
                            'date_joined', 'id', 'is_active')
        fields = ('username', 'email', 'first_name',
                  'last_name') + read_only_fields


class RegionSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = models.Region
        fields = ('slug', 'region', 'country')


class SubjectSerializer(rest_framework.serializers.ModelSerializer):
    additional_fields = ('region', 'country', 'sex',
                         'species',)
    class Meta:
        model = models.Subject
        fields = ('id', 'name', 'subject_type', 'subject_subtype')

    def to_representation(self, instance):
        rep = super(SubjectSerializer, self).to_representation(instance)
        additional = instance.additional
        additional = {k: additional[k] for k in self.additional_fields
                      if k in additional}
        rep.update(additional)
        if self.context and 'tracks_available' in self.context:
            rep['tracks_available'] = self.context['tracks_available']
            if 'last_position' in self.context:
                last_position = self.context['last_position']
                first_position = self.context['first_position']
                rep['last_position_date'] = last_position.recorded_at
                rep['last_position'] = make_feature(self.context['request'],
                                                    last_position.location,
                                                    instance,
                                                    time=last_position.recorded_at)
                rep['tracks_range'] = (first_position.recorded_at,
                                       last_position.recorded_at)
        elif self.context and self.context.get('show_last_position_date', None):
            last_position = instance.last_observation
            if last_position:
                rep['tracks_available'] = True
                rep['last_position_date'] = last_position.recorded_at
                rep['last_position'] = make_feature(self.context['request'],
                                                        last_position.location,
                                                        instance,
                                                        time=last_position.recorded_at)
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

        feature = make_feature(self.context['request'],
                               self.context['coordinates'], instance,
                               self.context['times'])
        rep = das_utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)
        return rep


class ObservationSerializer(rest_framework.serializers.ModelSerializer):
    class Meta:
        model = models.Observation
        fields = ('id', 'location', 'created_at', 'recorded_at', 'additional', 'source')
        id_field = False
        geo_field = 'location'


def make_feature(request, coordinates, subject, coordinate_times=None, time=None):
    is_point = isinstance(coordinates, Point)
    image_url = add_base_url(request, subject.image_url)
    feature = {
        'geometry': {
            'type': 'LineString' if not is_point else 'Point',
            'coordinates': coordinates if not is_point else coordinates.tuple
        },
        'type': 'Feature',
        'properties': {
            'title': subject.name,
            'subject_type': subject.subject_type,
            'subject_subtype': subject.subject_subtype
        },
    }
    properties = feature['properties']
    if hasattr(subject, 'color'):
        feature['style'] = {
            "color": subject.color,
            "iconUrl": image_url,
            "opacity": 1,
            "deprecating": "use https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0"
        }
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

