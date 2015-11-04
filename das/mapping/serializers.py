import os
import logging
import simplejson as json
import rest_framework.serializers as serializers
from raster.models import RasterLayer
import mapping.models as models


logger = logging.getLogger(__name__)

class RasterLayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = RasterLayer
        fields = ('id', 'name', 'description')

    def to_representation(self, instance):
        rep = super(RasterLayerSerializer, self).to_representation(instance)

        rep.update(dict(tilejson='2.1.0',
                        version='1.1.0',
                        autoscale=False,
                        ))

        #rep['scheme'] = 'tms'
        rep['legend'] = instance.legend.json
        try:
            rep['legend_json'] = json.loads(instance.legend.json)
        except json.JSONDecodeError:
            pass
        #rep['maxzoom'] = instance.metadata.max_zoom
        #rep['minzoom'] = 0
        #left, bottom, right, top
        #rep['bounds'] = [instance.metadata.uperleftx,
        #                 instance.metadata.uperlefty- instance.metadata.height,
        #                 instance.metadata.uperleftx + instance.metadata.width,
        #                 instance.metadata.uperlefty]

        request = self.context['request']
        url = '{0}/tms/tiles/{1}'.format(os.path.dirname(os.path.dirname(request._request.path)), str(instance.id))
        url = request._request.build_absolute_uri(url)
        url = '{0}/{{z}}/{{x}}/{{y}}.png'.format(url)
        rep['tiles'] = [url, ]

        return rep


class RedirectRasterLayerSerializer(serializers.Serializer):
    class Meta:
        model = models.TileLayer
        fields = ('id', 'name', 'version')

    def to_representation(self, instance):
        request = self.context['request']
        raster_layer = RasterLayer.objects.get(id=instance.attributes['rasterlayer_id'])
        rep = RasterLayerSerializer(raster_layer, context={'request': request}).data
        rep['version'] = instance.version
        return rep


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
    'raster': RedirectRasterLayerSerializer,
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