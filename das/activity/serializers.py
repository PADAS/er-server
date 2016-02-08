import rest_framework.serializers
from drf_extra_fields.geo_fields import PointField

import das_utils
import activity.models
from observations.serializers import make_feature, add_base_url


class EventSerializer(rest_framework.serializers.ModelSerializer):
    location = PointField(required=False)

    class Meta:
        model = activity.models.Event
        fields = (
        'id', 'location', 'created_at', 'updated_at', 'attributes', 'name', 'description', 'provenance', 'event_type')
        id_field = False
        geo_field = 'location'

    def to_representation(self, instance):

        feature = make_feature(self.context['request'],
                               instance.coordinates, instance, time=instance.time)
        rep = das_utils.json.empty_geojson_featurecollection()
        rep['features'].append(feature)
        return rep
