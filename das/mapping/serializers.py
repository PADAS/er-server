import os
import logging

import simplejson as json
from django.urls import reverse, NoReverseMatch
import rest_framework.serializers as serializers

import mapping.models as models


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