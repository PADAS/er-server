from django.contrib.gis.geos import Point

import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField

import das_utils

import activity.models


class EventSerializer(rest_framework.serializers.ModelSerializer):
    location = PointField(required=False)

    class Meta:
        model = activity.models.Event
        fields = (
        'id', 'location', 'created_at', 'updated_at', 'attributes', 'name', 'description', 'provenance', 'event_type')
        id_field = False
        geo_field = 'location'

    def to_representation(self, instance):

        feature = make_feature(self.context['request'], instance)

        rep = das_utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)
        return rep


def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = das_utils.add_base_url(request, event.image_url)
    feature = {
        'geometry': {
            'type': 'LineString' if not is_point else 'Point',
            'coordinates': event.coordinates if not is_point else event.coordinates.tuple
        },
        'type': 'Feature',
        'properties': {
            'title': event.name,
            'description': event.description,
            'datetime': event.time,
        },
    }
    properties = feature['properties']


    if hasattr(event, 'color'):
        feature['style'] = {
            "color": event.color,
            "iconUrl": image_url,
            "opacity": 1,
            "deprecating": "use https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0"
        }
        #see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties['stroke'] = event.color
        properties['stroke-opacity'] = 1.0
        properties['stroke-width'] = 2
        properties['image'] = image_url


    return feature

