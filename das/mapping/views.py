import hashlib
import logging
from itertools import chain

import simplejson as json
from rest_framework_extensions.etag.decorators import etag
from vectortiles.views import MVTView

from django.core.serializers import serialize
from django.db.models import Count, F
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

import mapping.serializers as serializers
from mapping import app_settings
from mapping.models import (
    DisplayCategory,
    Map,
    MBTiles,
    MBTilesNotFoundError,
    MissingTileError,
    SpatialFeature,
    TileLayer,
)
from mapping.permissions import LayerObjectPermissions
from mapping.vector_layers import SpatialFeatureLayer
from mapping.cache import build_tile_cache_key
from django.conf import settings
from utils.json import parse_bool

logger = logging.getLogger(__name__)


class FeatureListJsonView(APIView):
    """
    A simple list of vector layers available to the clients
    """

    def get(self, request):
        # todo:  add api docs
        response_data = {"features": []}
        include_hidden = parse_bool(request.GET.get("include_hidden", False))
        features = (
            SpatialFeature.objects.all()
            if include_hidden
            else SpatialFeature.objects.filter(feature_type__is_visible=True)
        )

        for feature in features:
            type_dict = dict(name=feature.feature_type.name, id=str(feature.feature_type.id))

            response_data["features"].append(
                {
                    "name": feature.name,
                    "type": type_dict,
                    "description": feature.description if feature.description else "",
                    "geojson_url": reverse("mapping:mapping-feature-geojson", args=[feature.id.hex]),
                }
            )
        return HttpResponse(json.dumps(response_data).encode("utf-8"), content_type="application/json")


class FeatureGeoJsonView(APIView):
    def get(self, request, id):
        include_hidden = parse_bool(request.GET.get("include_hidden", False))
        selected_feature = (
            SpatialFeature.objects.filter(id=id)
            if include_hidden
            else SpatialFeature.objects.filter(id=id).filter(feature_type__is_visible=True)
        )

        feature = serialize(
            "geojson",
            selected_feature,
            properties={"name": "title", "default_presentation": "presentation"},
            geometry_field="feature_geometry",
        )
        return HttpResponse(feature.encode("utf-8"), content_type="application/json")


class FeatureSetListJsonView(APIView):
    """
    A simple list of featuresets available to the clients
    """

    def get(self, request):
        def feature_types(featureset, include_hidden, summarize_features):
            if include_hidden:
                feature_types_qs = featureset.spatialfeaturetype_set.annotate(
                    spatialfeature_count=Count("spatialfeature")
                ).all()
            else:
                feature_types_qs = featureset.spatialfeaturetype_set.annotate(
                    spatialfeature_count=Count("spatialfeature")
                ).filter(is_visible=True)

            for t in feature_types_qs:
                features_qs = SpatialFeature.objects.filter(feature_type=t)
                if not include_hidden:
                    features_qs = features_qs.filter(feature_type__is_visible=True)

                featureTypeDict = {
                    "name": t.name,
                    "id": str(t.id),
                    "feature_count": t.spatialfeature_count,
                }

                if summarize_features:
                    # Correctly add the 'feature_summaries' key to the dictionary
                    featureTypeDict["feature_summaries"] = [
                        {
                            "name": f.name,
                            "bounds": f.feature_geometry.extent if f.feature_geometry else None,
                        }
                        for f in features_qs
                    ]

                yield featureTypeDict

        include_hidden = parse_bool(request.GET.get("include_hidden", False))
        summarize_features = parse_bool(request.GET.get("summarize_features", False))
        response_data = {"features": []}
        featuresets = DisplayCategory.objects.all()

        for featureset in featuresets:
            response_data["features"].append(
                {
                    "name": featureset.name,
                    "id": str(featureset.id),
                    "types": list(feature_types(featureset, include_hidden, summarize_features)),
                    "description": featureset.description if featureset.description else "",
                    "geojson_url": reverse("mapping:mapping-featureset-geojson", args=[featureset.id.hex]),
                }
            )
        return HttpResponse(json.dumps(response_data).encode("utf-8"), content_type="application/json")


def calculate_featureset_etag(view_instance, view_method, request, args, kwargs):
    include_hidden = parse_bool(request.GET.get("include_hidden", False))
    featureset = get_object_or_404(DisplayCategory, id=kwargs["id"])
    field_list = ("updated_at", "feature_type__updated_at")
    qs = (
        SpatialFeature.objects.filter(feature_type__display_category=featureset)
        if include_hidden
        else SpatialFeature.objects.filter(feature_type__display_category=featureset).filter(
            feature_type__is_visible=True
        )
    )
    objects = qs.values(*field_list)
    etag = ",".join((str(f["updated_at"]) + str(f["feature_type__updated_at"]) for f in objects))

    etag += str(featureset.updated_at)
    return hashlib.md5(etag.encode("utf-8")).hexdigest()


class FeatureSetGeoJsonView(APIView):
    parser_classes = (JSONParser,)
    lookup_field = "id"

    @etag(etag_func=calculate_featureset_etag)
    def get(self, request, **kwargs):
        featureset = get_object_or_404(DisplayCategory, id=kwargs["id"])
        include_hidden = parse_bool(request.GET.get("include_hidden", False))

        # Filter out null geometries instead of using expensive spatial intersection
        querysets = (
            SpatialFeature.objects.filter(feature_type__display_category=featureset)
            .exclude(feature_geometry__isnull=True)
            .filter(feature_geometry__bboverlaps=F("feature_geometry"))
            if include_hidden
            else SpatialFeature.objects.filter(feature_type__display_category=featureset)
            .filter(feature_type__is_visible=True)
            .filter(feature_geometry__bboverlaps=F("feature_geometry"))
            .exclude(feature_geometry__isnull=True)
        )

        # So type-name can appear in geojson properties.
        querysets = (querysets.prefetch_related("feature_type").annotate(type_name=F("feature_type__name")),)

        feature = serialize(
            "geojson",
            list(chain(*querysets)),
            properties={
                "name": "title",
                "default_presentation": "presentation",
                "type_name": "type_name",
            },
            geometry_field="feature_geometry",
        )

        return HttpResponse(feature.encode("utf-8"), content_type="application/json")

    def post(self, request, format=None):
        pass


class MapListJsonView(generics.ListAPIView):
    """
    List of available maps. A Map defines the center location, zoom level and
    tile layers.
    """

    queryset = Map.objects.all()
    serializer_class = serializers.MapSerializer

    def get_queryset(self):
        return Map.objects.all()


class LayerListJsonView(generics.ListCreateAPIView):
    """
    List of available map layers.
    """

    serializer_class = serializers.TileLayerSerializer
    permission_classes = (LayerObjectPermissions,)

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        return TileLayer.objects.all().by_ordernum()


class LayerJsonView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    serializer_class = serializers.TileLayerSerializer
    permission_classes = (LayerObjectPermissions,)

    def get_queryset(self):
        return TileLayer.objects.all()


class SpatialFeatureTileView(MVTView):
    """
    Vector tile endpoint for SpatialFeature geometries.

    Returns Mapbox Vector Tiles (MVT) containing spatial features for the given tile coordinates.

    Cache strategy:
    - Short server-side TTL (5 minutes) for fresh data
    - Long client-side cache headers (1 hour) for performance
    - Users can refresh with hard reload if needed
    """

    layer_classes = [SpatialFeatureLayer]
    permission_classes = (LayerObjectPermissions,)

    # Server-side cache TTL (seconds). Keep a little longer than client max-age so we can
    # usually revalidate from server cache rather than hitting the DB immediately.
    cache_timeout_seconds = 240  # 4 minutes server cache
    # Client cache controls (freshness window + stale-while-revalidate window)
    client_max_age_seconds = 180  # 3 minutes fresh
    client_stale_while_revalidate_seconds = 180  # serve stale up to another 3 minutes while revalidating
    client_stale_if_error_seconds = 180  # serve stale if origin errors for same window

    def get(self, request, z, x, y):
        layer_ids = [lc.id for lc in self.layer_classes]
        try:
            cache_key = build_tile_cache_key(
                request,
                z,
                x,
                y,
                layer_ids,
                cache_version=getattr(settings, "VECTOR_TILE_CACHE_VERSION", "1"),
            )
        except ValueError:
            return HttpResponse(
                status=401, headers={"WWW-Authenticate": "Bearer realm=vector-tiles"}
            )  # Fast reject unauthenticated / malformed token requests
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            # Reconstruct fresh response object to avoid mutating cached instance
            content, content_type = cached_payload
            resp = HttpResponse(content, content_type=content_type)
            resp["Cache-Control"] = (
                "public, max-age="
                f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
                f"stale-if-error={self.client_stale_if_error_seconds}"
            )
            resp["X-Cache"] = "HIT"
            resp["Vary"] = "Authorization"
            return resp
        response = super().get(request, z, x, y)
        if response.status_code == 200 and response.get("Content-Type", "").startswith("application/x-protobuf"):
            cache.set(cache_key, (response.content, response.get("Content-Type")), timeout=self.cache_timeout_seconds)
            response["X-Cache"] = "MISS"
        else:
            response["X-Cache"] = "BYPASS"
        response["Cache-Control"] = (
            "public, max-age="
            f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
            f"stale-if-error={self.client_stale_if_error_seconds}"
        )
        response["Vary"] = "Authorization"
        return response


#
# Don't secure the following until we can have Leaflet use auth tokens
# with this api for tiles
#
@api_view(
    [
        "GET",
    ]
)
@permission_classes([])
def tile(request, name, z, x, y, catalog=None):
    """Serve a single image tile"""
    try:
        mbtiles = MBTiles(name, catalog)
        data = mbtiles.tile(z, x, y)
        response = HttpResponse(content_type="image/png")
        response.write(data)
        return response
    except MBTilesNotFoundError as e:
        logger.warning(e)
    except MissingTileError:
        logger.warning(_("Tile %s not available in %s") % ((z, x, y), name))
        if not app_settings.MBTILES["missing_tile_404"]:
            return HttpResponse(content_type="image/png")
    raise Http404


@api_view(
    [
        "GET",
    ]
)
@permission_classes([])
def preview(request, name, catalog=None):
    try:
        mbtiles = MBTiles(name, catalog)
        z, x, y = mbtiles.center_tile()
        return tile(request, name, z, x, y)
    except MBTilesNotFoundError as e:
        logger.warning(e)
    raise Http404


@api_view(
    [
        "GET",
    ]
)
@permission_classes([])
def grid(request, name, z, x, y, catalog=None):
    """Serve a single UTF-Grid tile"""
    callback = request.GET.get("callback", None)
    try:
        mbtiles = MBTiles(name, catalog)
        grid_content = mbtiles.grid(z, x, y, callback).encode("utf-8")
        return HttpResponse(grid_content, content_type="application/javascript; charset=utf8")
    except MBTilesNotFoundError as e:
        logger.warning(e)
    except MissingTileError:
        logger.warning(_("Grid tile %s not available in %s") % ((z, x, y), name))
    raise Http404


@api_view(
    [
        "GET",
    ]
)
@permission_classes([])
def tilejson(request, name, catalog=None):
    """Serve the map configuration as TileJSON"""
    callback = request.GET.get("callback", None)
    try:
        mbtiles = MBTiles(name, catalog)
        tilejson = mbtiles.tilejson(request)
        tilejson = json.dumps(tilejson)
        if callback:
            tilejson = "%s(%s);" % (callback, tilejson)
        return HttpResponse(tilejson.encode("utf-8"), content_type="application/javascript; charset=utf8")
    except MBTilesNotFoundError as e:
        logger.warning(e)
    raise Http404
