import os
import logging

import simplejson as json
from django.urls import reverse, NoReverseMatch
import rest_framework.serializers as serializers

import mapping.models as models

import utils

logger = logging.getLogger(__name__)


class MBTilesSerializer(serializers.Serializer):
    def to_representation(self, instance):
        rep = {}
        mbtiles_name = instance.attributes['mbtiles_name']
        mbtiles = models.MBTiles(mbtiles_name)
        request = self.context['request']
        return mbtiles.tilejson(request)


class ExternalTileSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TileLayer
        fields = ('id', 'name', 'version')

    def to_representation(self, instance):
        rep = super(ExternalTileSerializer, self).to_representation(instance)
        request = self.context['request']
        rep.update(instance.attributes)
        return rep


TILELAYER_SERIALIZERS = {
    'mbtiles': MBTilesSerializer,
    'external': ExternalTileSerializer
}


class TileLayerSerializer(serializers.Serializer):
    def to_representation(self, instance):
        request = self.context['request']

        rep = TILELAYER_SERIALIZERS[instance.tile_type](
            instance, context={'request': request}
        )
        return rep


class MapSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Map
        fields = ('id', 'name', 'zoom')

    def to_representation(self, instance):
        rep = super(MapSerializer, self).to_representation(instance)
        rep.update(instance.attributes)
        rep['center'] = instance.center.tuple
        request = self.context['request']
        tile_layers = TileLayerSerializer(
            instance.tilelayer_set.all(), many=True, context={'request': request})

        layers = []
        for t in tile_layers.data:
            try:
                layers.append(t.data)
            except:
                logger.exception("Failed to serialize map")

        rep['layers'] = layers
        return rep


class FeatureTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeatureType
        fields = ('id', 'name')  # , 'presentation',)


# from django.contrib.gis.geos import (
#     GeometryCollection, GEOSException, GEOSGeometry, LineString,
#     MultiLineString, MultiPoint, MultiPolygon, Point, Polygon,
# )
from django.core.serializers import serialize
# class FeatureGeometrySerializer(serializers.Serializer):
#
#     def to_representation(self, instance):
#         return super().to_representation(instance)


class SpatialFeatureSerializer(serializers.ModelSerializer):

    # feature_geometry = FeatureGeometrySerializer()
    feature_type = FeatureTypeSerializer()

    class Meta:
        model = models.SpatialFeature
        fields = ('id', 'name', 'feature_type', )  # 'feature_geometry',)

    def to_representation(self, instance):
        # rep = super().to_representation(instance)
        return json.loads(serialize('geojson', (instance,), properties={}, geometry_field='feature_geometry',))

        return rep


class SpatialFeatureGroupStaticSerializer(serializers.ModelSerializer):

    features = SpatialFeatureSerializer(many=True)

    class Meta:
        model = models.SpatialFeatureGroupStatic
        fields = ('name', 'features', 'description')

    def to_representation(self, instance):

        rep = super().to_representation(instance)

        if 'request' in self.context:
            rep['url'] = utils.add_base_url(self.context['request'],
                                            reverse('mapping:spatialfeaturegroup-view',
                                                    args=[instance.id, ]))

        return rep
