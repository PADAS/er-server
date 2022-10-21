import hashlib
import logging
from itertools import chain

import simplejson as json
from rest_framework_extensions.etag.decorators import etag

from django.core.serializers import serialize
from django.db.models import F
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

import mapping.serializers as serializers
from mapping import app_settings
from mapping.models import (DisplayCategory, Map, MBTiles,
                            MBTilesNotFoundError, MissingTileError,
                            SpatialFeature, TileLayer)
from mapping.permissions import LayerObjectPermissions
from utils.json import parse_bool

logger = logging.getLogger(__name__)


class FeatureListJsonView(APIView):
    """
    A simple list of vector layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {'features': []}
        include_hidden = parse_bool(request.GET.get('include_hidden', False))
        features = SpatialFeature.objects.all() if include_hidden else SpatialFeature.objects.filter(
            feature_type__is_visible=True)

        for feature in features:
            type_dict = dict(name=feature.feature_type.name,
                             id=str(feature.feature_type.id))

            print(f"\nHEX: {feature.id.hex}\n")
            response_data['features'].append({
                'name': feature.name,
                'type': type_dict,
                'description': feature.description if feature.description else '',
                'geojson_url': reverse('mapping:mapping-feature-geojson', args=[feature.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


class FeatureGeoJsonView(APIView):
    def get(self, request, id):
        include_hidden = parse_bool(request.GET.get('include_hidden', False))
        selected_feature = SpatialFeature.objects.filter(id=id) if include_hidden \
            else SpatialFeature.objects.filter(id=id).filter(feature_type__is_visible=True)

        feature = serialize('geojson',
                            selected_feature,
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
        def feature_types(featureset, include_hidden):
            feature_types_qs = featureset.spatialfeaturetype_set.all() if include_hidden \
                else featureset.spatialfeaturetype_set.filter(is_visible=True)

            for t in feature_types_qs:
                yield dict(name=t.name, id=str(t.id), feature_count=t.feature_count)

        include_hidden = parse_bool(request.GET.get('include_hidden', False))
        response_data = {'features': []}
        featuresets = DisplayCategory.objects.all()

        for featureset in featuresets:
            response_data['features'].append({
                'name': featureset.name,
                'id': str(featureset.id),
                'types': list(feature_types(featureset, include_hidden)),
                'description': featureset.description if featureset.description else '',
                'geojson_url': reverse('mapping:mapping-featureset-geojson', args=[featureset.id.hex]),
            })
        return HttpResponse(json.dumps(response_data), content_type='application/json')


def calculate_featureset_etag(view_instance, view_method, request, args, kwargs):
    include_hidden = parse_bool(request.GET.get('include_hidden', False))
    featureset = DisplayCategory.objects.get(id=kwargs['id'])
    field_list = ('updated_at', 'feature_type__updated_at')
    qs = SpatialFeature.objects.filter(
        feature_type__display_category=featureset) if include_hidden else SpatialFeature.objects.filter(
        feature_type__display_category=featureset).filter(feature_type__is_visible=True)
    objects = qs.values(*field_list)
    etag = ','.join((str(f['updated_at']) + str(f['feature_type__updated_at'])
                     for f in objects))

    etag += str(featureset.updated_at)
    return hashlib.md5(etag.encode('utf-8')).hexdigest()


class FeatureSetGeoJsonView(APIView):
    parser_classes = (JSONParser,)
    lookup_field = 'id'

    @etag(etag_func=calculate_featureset_etag)
    def get(self, request, **kwargs):
        # todo:  better 404 handling, what to do with empty featureset
        featureset = DisplayCategory.objects.get(id=kwargs['id'])
        include_hidden = parse_bool(request.GET.get('include_hidden', False))
        querysets = SpatialFeature.objects.filter(
            feature_type__display_category=featureset) if include_hidden else SpatialFeature.objects.filter(
            feature_type__display_category=featureset).filter(feature_type__is_visible=True)
        # So type-name can appear in geojson properties.
        querysets = (querysets.prefetch_related('feature_type').annotate(
            type_name=F('feature_type__name')),)

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


class LayerListJsonView(generics.ListCreateAPIView):
    """
    List of available map layers.
    """
    queryset = TileLayer.objects.all().by_ordernum()
    serializer_class = serializers.TileLayerSerializer
    permission_classes = (LayerObjectPermissions,)

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST, )
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LayerJsonView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = 'id'
    serializer_class = serializers.TileLayerSerializer
    queryset = TileLayer.objects.all()
    permission_classes = (LayerObjectPermissions,)


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
    except MissingTileError:
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
