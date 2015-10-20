import os
import rest_framework.serializers as serializers
from raster.models import RasterLayer


class RasterLayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = RasterLayer
        fields = ('id', 'name', 'description')

    def to_representation(self, instance):
        rep = super(RasterLayerSerializer, self).to_representation(instance)

        rep.update(dict(tilejson='2.1.0',
                        version='1.0.0',
                        ))

        #rep['scheme'] = 'tms'
        rep['legend'] = instance.legend.json
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
