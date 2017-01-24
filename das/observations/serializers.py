from django.contrib.gis.geos import Point
import rest_framework.serializers

from core.serializers import ContentTypeField
from observations import models
import utils.json
import datetime
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

        queryset = queryset.order_by('name')

        rep = super().to_representation(instance)
        data = [data_serializer.to_representation(s)
                for s in queryset]
        rep[contained_field] = data
        return rep


def get_subject_display(subject):
    return subject.name


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
            permission_check_instance = instance
            # If the subject list has already been filtered, we don't need to
            # check permissions on each subject so pass None and cache the result
            try:
                if self.instance._hints.get('subjects_filtered', False):
                    permission_check_instance = None
            except:
                permission_check_instance = None

            # Find the min and max boundaries for track data
            oldest_track_age = -1
            newest_track_age = 999

            for permission_tuple in models.Subject.VIEW_BEGIN_WINDOWS:
                if permission_tuple[1] > oldest_track_age and user.has_perm(permission_tuple[0]):
                    oldest_track_age = permission_tuple[1]

            for permission_tuple in models.Subject.VIEW_END_WINDOWS:
                if permission_tuple[1] < newest_track_age and user.has_perm(permission_tuple[0]):
                    newest_track_age = permission_tuple[1]


            if newest_track_age > 0:
                last_position = instance.subjectstatus_set.get_delayed(newest_track_age * 24)
            else:
                last_position = instance.subjectstatus_set.get_last()
                rep['image_url'] = instance.image_url

            if oldest_track_age < 999 and last_position is not None and last_position.recorded_at < datetime.datetime.now() - datetime.timedelta(days=oldest_track_age):
                    last_position = None

            rep['tracks_available'] = bool(last_position)

            if last_position:
                first_position = instance.subjectstatus_set.get_delayed()

                if 'state' in last_position.additional:
                    rep['state'] = last_position.additional['state']
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

        # TODO: Review with Shawn, wrt to recent changes in SubjectTracksView.
        image_url = (self.context.get('subject') or instance).image_url

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

