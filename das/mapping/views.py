import itertools
import simplejson as json
import logging
from itertools import chain

from django.core.serializers import serialize
from django.core.urlresolvers import reverse
from django.http import HttpResponse, Http404
from django.views.generic import View
from django.utils.translation import ugettext_lazy as _
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response


from raster.models import RasterLayer
from mapping.models import PolygonFeature, LineFeature, PointFeature, FeatureSet
from mapping.models import MBTiles, MBTilesNotFoundError, MissingTileError
import mapping.serializers as serializers
from mapping import app_settings

logger = logging.getLogger(__name__)


class FeatureListJsonView(APIView):
    """
    A simple list of vector layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {'das_api_stuff': 'goes_here', 'features': []}
        features = list(chain(PolygonFeature.objects.all(), LineFeature.objects.all(), PointFeature.objects.all()))
        for feature in features:
            response_data['features'].append({
                'name': feature.name,
                'type': feature.type.name,
                'description': feature.description if feature.description else '',
                'geojson_url': reverse('mapping-feature-geojson', args=[feature.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


class FeatureGeoJsonView(APIView):
    def get(self, request, feature_id):
        feature = serialize('geojson',
                            list(chain(PolygonFeature.objects.filter(id=feature_id),
                                       LineFeature.objects.filter(id=feature_id),
                                       PointFeature.objects.filter(id=feature_id))),
                            fields='name, presentation, feature_geometry,'
                            )
        return HttpResponse(feature, content_type='application/json')


class FeatureSetListJsonView(APIView):
    """
    A simple list of featuresets available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {'das_api_stuff': 'goes_here', 'features': []}
        featuresets = FeatureSet.objects.all()
        for featureset in featuresets:
            response_data['features'].append({
                'name': featureset.name,
                'type': featureset.type.name,
                'description': featureset.description if featureset.description else '',
                'geojson_url': reverse('mapping-featureset-geojson', args=[featureset.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


class FeatureSetGeoJsonView(APIView):
    def get(self, request, featureset_id):
        # todo:  better 404 handling, what to do with empty featureset
        featureset = FeatureSet.objects.get(id=featureset_id)
        feature = serialize('geojson',
                            list(chain(PolygonFeature.objects.filter(featureset=featureset),
                                       LineFeature.objects.filter(featureset=featureset),
                                       PointFeature.objects.filter(featureset=featureset))),
                            fields='name, presentation, feature_geometry,'
                            )
        return HttpResponse(feature, content_type='application/json')


OSM_GEOJSON = {'name': 'OpenStreetMap',
               'tiles': ['http://b.tile.openstreetmap.com/{z}/{x}/{y}.png',],
               'maxZoom': 18,
               'attribution': 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, '
                              '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a> ',
               'id': 'examples.map-20v6611k'}

class MapListJsonView(APIView):
    """
    A simple list of raster and mbtile layers available to the clients
    """
    def get(self, request, *args, **kwargs):
        rasters = RasterLayer.objects.all()
        rasters_s = serializers.RasterLayerSerializer(rasters, many=True,
                                            context={'request': request})

        mbtiles = MBTiles.objects.all()
        mbtiles_s = list(m.tilejson(request._request) for m in mbtiles)

        return Response(list(itertools.chain(rasters_s.data, mbtiles_s, [OSM_GEOJSON,])))


@api_view(['GET',])
def tile(request, name, z, x, y, catalog=None):
    """ Serve a single image tile """
    try:
        mbtiles = MBTiles(name, catalog)
        data = mbtiles.tile(z, x, y)
        response = HttpResponse(content_type='image/png')
        response.write(data)
        return response
    except MBTilesNotFoundError as e:
        logger.warning(e)
    except MissingTileError as e:
        logger.warning(_("Tile %s not available in %s") % ((z, x, y), name))
        if not app_settings.MBTILES['missing_tile_404']:
            return HttpResponse(content_type="image/png")
    raise Http404

@api_view(['GET',])
def preview(request, name, catalog=None):
    try:
        mbtiles = MBTiles(name, catalog)
        z, x, y = mbtiles.center_tile()
        return tile(request, name, z, x, y)
    except MBTilesNotFoundError as e:
        logger.warning(e)
    raise Http404


@api_view(['GET',])
def grid(request, name, z, x, y, catalog=None):
    """ Serve a single UTF-Grid tile """
    callback = request.GET.get('callback', None)
    try:
        mbtiles = MBTiles(name, catalog)
        return HttpResponse(
            mbtiles.grid(z, x, y, callback),
            content_type = 'application/javascript; charset=utf8'
        )
    except MBTilesNotFoundError as e:
        logger.warning(e)
    except MissingTileError:
        logger.warning(_("Grid tile %s not available in %s") % ((z, x, y), name))
    raise Http404


@api_view(['GET',])
def tilejson(request, name, catalog=None):
    """ Serve the map configuration as TileJSON """
    callback = request.GET.get('callback', None)
    try:
        mbtiles = MBTiles(name, catalog)
        tilejson = mbtiles.tilejson(request)
        tilejson = json.dumps(tilejson)
        if callback:
            tilejson = '%s(%s);' % (callback, tilejson)
        return HttpResponse(tilejson,
                            content_type='application/javascript; charset=utf8')
    except MBTilesNotFoundError as e:
        logger.warning(e)
    raise Http404