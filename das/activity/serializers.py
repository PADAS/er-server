from django.contrib.gis.geos import Point
from django.core.urlresolvers import reverse

import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField

import das_utils

import activity.models


class EventSerializer(rest_framework.serializers.ModelSerializer):
    # Using PointField here provides the magic to convert between a json {lat/lon} and our internal representation.
    location = PointField(required=False)

    class Meta:
        model = activity.models.Event
        fields = (
            'id', 'location', 'time', 'name', 'description', 'provenance', 'event_type', 'priority', 'attributes',
            'image_url')
        id_field = False
        geo_field = 'location'

    def to_representation(self, event):
        rep = super().to_representation(event)
        rep['url'] = das_utils.add_base_url(self.context['request'], reverse('event-view', args=[event.id, ]))

        if event.location is not None:
            geodata = make_feature(self.context['request'], event)
            rep['geojson'] = geodata
        return rep


def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = das_utils.add_base_url(request, event.image_url)
    feature = das_utils.json.empty_geojson_feature()
    feature['geometry'] = {
        'type': 'LineString' if not is_point else 'Point',
        'coordinates': event.coordinates if not is_point else event.coordinates.tuple
    }
    feature['type'] = 'Feature'
    feature['properties'] = {
        'title': event.name,
        'datetime': event.time,
        'image': event.image_url
    }

    properties = feature['properties']
    if hasattr(event, 'color'):
        feature['style'] = {
            "color": event.color,
            "iconUrl": image_url,
            "opacity": 1,
            "deprecating": "use https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0"
        }
        # see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties['stroke'] = event.color
        properties['stroke-opacity'] = 1.0
        properties['stroke-width'] = 2
        properties['image'] = image_url

    return feature
