import hashlib
import logging
from itertools import chain

import simplejson as json
from django.conf import settings
from django.core.serializers import serialize
from django.db.models import F
from django.http import HttpResponse, Http404
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.views import APIView
from rest_framework_extensions.etag.decorators import etag

import mapping.serializers as serializers
from mapping import app_settings
from mapping.models import MBTiles, MBTilesNotFoundError, MissingTileError, Map, TileLayer
from mapping.models import PolygonFeature, LineFeature, PointFeature, FeatureSet, SpatialFeature, DisplayCategory

logger = logging.getLogger(__name__)
MAPPING_FEATURES_V2 = getattr(settings, 'MAPPING_FEATURES_V2', False)


class FeatureListJsonView(APIView):
    """
    A simple list of vector layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {'features': []}
        features = SpatialFeature.objects.all() if MAPPING_FEATURES_V2 \
            else list(chain(PolygonFeature.objects.all(),
                            LineFeature.objects.all(),
                            PointFeature.objects.all()))

        for feature in features:
            type_dict = dict(name=feature.feature_type.name, id=str(feature.feature_type.id)) if MAPPING_FEATURES_V2 \
                else dict(name=feature.type.name, id=str(feature.type.id))

            response_data['features'].append({
                'name': feature.name,
                'type': type_dict,
                'description': feature.description if feature.description else '',
                'geojson_url': reverse('mapping:mapping-feature-geojson', args=[feature.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


class FeatureGeoJsonView(APIView):
    def get(self, request, id):
        all_features = SpatialFeature.objects.filter(id=id) if MAPPING_FEATURES_V2 \
            else list(chain(PolygonFeature.objects.filter(id=id),
                            LineFeature.objects.filter(id=id),
                            PointFeature.objects.filter(id=id)))

        feature = serialize('geojson',
                            all_features,
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
            feature_types_qs = featureset.spatialfeaturetype_set.all() if MAPPING_FEATURES_V2 \
                else featureset.types.all()

            for t in feature_types_qs:
                yield dict(name=t.name, id=str(t.id), feature_count=t.feature_count)

        response_data = {'features': []}
        featuresets = DisplayCategory.objects.all() if MAPPING_FEATURES_V2 else FeatureSet.objects.all()

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

    if MAPPING_FEATURES_V2:
        featureset = DisplayCategory.objects.get(id=kwargs['id'])
        field_list = ('updated_at', 'feature_type__updated_at')
        objects = SpatialFeature.objects.filter(feature_type__display_category=featureset).values(*field_list)
        etag = ','.join((str(f['updated_at']) + str(f['feature_type__updated_at'])
                         for f in objects))
    else:
        featureset = FeatureSet.objects.get(id=kwargs['id'])
        field_list = ('updated_at', 'type__updated_at')
        objects = chain(PolygonFeature.objects.filter(featureset=featureset).values(*field_list),
                        LineFeature.objects.filter(featureset=featureset).values(*field_list),
                        PointFeature.objects.filter(featureset=featureset).values(*field_list))
        etag = ','.join((str(f['updated_at']) + str(f['type__updated_at'])
                         for f in objects))
    etag += str(featureset.updated_at)
    return hashlib.md5(etag.encode('utf-8')).hexdigest()


class FeatureSetGeoJsonView(APIView):
    parser_classes = (JSONParser,)
    lookup_field = 'id'

    @etag(etag_func=calculate_featureset_etag)
    def get(self, request, **kwargs):
        # todo:  better 404 handling, what to do with empty featureset
        if MAPPING_FEATURES_V2:
            featureset = DisplayCategory.objects.get(id=kwargs['id'])
            querysets = (SpatialFeature.objects.filter(feature_type__display_category=featureset),)
            # So type-name can appear in geojson properties.
            querysets = (q.prefetch_related('feature_type').annotate(
                type_name=F('feature_type__name')) for q in querysets)
        else:
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
