import simplejson as json
import logging
from itertools import chain
import hashlib

from django.db.models import F

from django.core.serializers import serialize
from django.urls import reverse
from django.http import HttpResponse, Http404
from django.utils.translation import ugettext_lazy as _
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from rest_framework_extensions.etag.decorators import etag

from mapping.models import PolygonFeature, LineFeature, PointFeature, FeatureSet
from mapping.models import MBTiles, MBTilesNotFoundError, MissingTileError, Map, TileLayer
import mapping.serializers as serializers
from mapping import app_settings

logger = logging.getLogger(__name__)


class FeatureListJsonView(APIView):
    """
    A simple list of vector layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {'features': []}
        features = list(chain(PolygonFeature.objects.all(),
                              LineFeature.objects.all(), PointFeature.objects.all()))
        for feature in features:
            response_data['features'].append({
                'name': feature.name,
                'type': dict(name=feature.type.name, id=str(feature.type.id)),
                'description': feature.description if feature.description else '',
                'geojson_url': reverse('mapping:mapping-feature-geojson', args=[feature.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


class FeatureGeoJsonView(APIView):
    def get(self, request, id):
        feature = serialize('geojson',
                            list(chain(PolygonFeature.objects.filter(id=id),
                                       LineFeature.objects.filter(id=id),
                                       PointFeature.objects.filter(id=id))),
                            properties={'name': 'title',
                                        'default_presentation': 'presentation'},
                            geometry_field='feature_geometry'
                            )
        return HttpResponse(feature, content_type='application/json')


class FeatureSetListJsonView(APIView):
    """
    A simple list of featuresets available to the clients
    """

    def get(self, request):
        def feature_types(featureset):
            for t in featureset.types.all():
                yield dict(name=t.name, id=str(t.id))

        response_data = {'features': []}
        featuresets = FeatureSet.objects.all()
        for featureset in featuresets:
            response_data['features'].append({
                'name': featureset.name,
                'id': str(featureset.id),
                'types': list(feature_types(featureset)),
                'description': featureset.description if featureset.description else '',
                'geojson_url': reverse('mapping:mapping-featureset-geojson', args=[featureset.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


def calculate_featureset_etag(view_instance, view_method, request, args, kwargs):
    featureset = FeatureSet.objects.get(id=kwargs['id'])
    objects = chain(PolygonFeature.objects.filter(featureset=featureset),
                    LineFeature.objects.filter(featureset=featureset),
                    PointFeature.objects.filter(featureset=featureset))
    etag = ','.join((str(f.updated_at) + str(f.type.updated_at)
                     for f in objects))
    etag += str(featureset.updated_at)
    return hashlib.md5(etag.encode('utf-8')).hexdigest()


class FeatureSetGeoJsonView(APIView):
    parser_classes = (JSONParser,)
    lookup_field = 'id'

    @etag(etag_func=calculate_featureset_etag)
    def get(self, request, **kwargs):
        # todo:  better 404 handling, what to do with empty featureset
        featureset = FeatureSet.objects.get(id=kwargs['id'])

        querysets = (PolygonFeature.objects.filter(featureset=featureset),
                     LineFeature.objects.filter(featureset=featureset),
                     PointFeature.objects.filter(featureset=featureset))
        # So type-name can appear in geojson properties.
        querysets = (q.prefetch_related('type').annotate(
            type_name=F('type__name')) for q in querysets)

        feature = serialize('geojson',
                            list(chain(*querysets)),
                            properties={'name': 'title',
                                        'default_presentation': 'presentation',
                                        'type_name': 'type_name',
                                        },
                            geometry_field='feature_geometry'
                            )

        return HttpResponse(feature, content_type='application/json')

    def post(self, request, format=None):
        pass


class MapListJsonView(generics.ListAPIView):
    """
    List of available maps. A Map defines the center location, zoom level and
    tile layers.
    """
    queryset = Map.objects.all()
    serializer_class = serializers.MapSerializer


class LayerListJsonView(generics.ListAPIView):
    """
    List of available map layers.
    """
    queryset = TileLayer.objects.all().by_ordernum()
    serializer_class = serializers.TileLayerSerializer


#
# Don't secure the following until we can have Leaflet use auth tokens
# with this api for tiles
#
@api_view(['GET', ])
@permission_classes([])
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


@api_view(['GET', ])
@permission_classes([])
def preview(request, name, catalog=None):
    try:
        mbtiles = MBTiles(name, catalog)
        z, x, y = mbtiles.center_tile()
        return tile(request, name, z, x, y)
    except MBTilesNotFoundError as e:
        logger.warning(e)
    raise Http404


@api_view(['GET', ])
@permission_classes([])
def grid(request, name, z, x, y, catalog=None):
    """ Serve a single UTF-Grid tile """
    callback = request.GET.get('callback', None)
    try:
        mbtiles = MBTiles(name, catalog)
        return HttpResponse(
            mbtiles.grid(z, x, y, callback),
            content_type='application/javascript; charset=utf8'
        )
    except MBTilesNotFoundError as e:
        logger.warning(e)
    except MissingTileError:
        logger.warning(_("Grid tile %s not available in %s") %
                       ((z, x, y), name))
    raise Http404


@api_view(['GET', ])
@permission_classes([])
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
