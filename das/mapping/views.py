from __future__ import annotations

import hashlib
import logging
from itertools import chain
from typing import ClassVar

import simplejson as json
from rest_framework_extensions.etag.decorators import etag

from django.core.serializers import serialize
from django.db.models import Count, F, Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

import mapping.serializers as serializers
from das_server.views import CustomSchema, DRFMVTView
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
from utils.cache import (
    build_tile_cache_key,
    get_effective_cache_version,
    get_vector_tile_cache,
)
from utils.drf import DeprecatedEndpointMixin, create_json_response
from utils.json import parse_bool
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.providers import get_tenant_data_by_host

logger = logging.getLogger(__name__)


def hashtext_uuid(uuid_value):
    """
    Calculate a hashtext value for a UUID that matches PostgreSQL's hashtext function.
    This is a fallback for when database annotations aren't available.
    """
    # Convert UUID to string and encode as UTF-8
    uuid_str = str(uuid_value).encode("utf-8")
    # Create a hash similar to PostgreSQL's hashtext function
    hash_value = int(hashlib.md5(uuid_str).hexdigest(), 16) % (2**31)
    return hash_value


class FeatureListJsonView(APIView):
    """
    A simple list of vector layers available to the clients
    """

    _SORT_FIELD_MAP: ClassVar[dict[str, str]] = {
        "name": "name",
        "-name": "-name",
        "feature_type": "feature_type__name",
        "-feature_type": "-feature_type__name",
    }

    def get(self, request: Request) -> HttpResponse:
        include_hidden = parse_bool(request.GET.get("include_hidden", False))
        feature_type_id = request.GET.get("feature_type")
        feature_set_id = request.GET.get("feature_set")
        sort_by = request.GET.get("sort_by", "name")

        qs = SpatialFeature.objects.select_related("feature_type")
        if not include_hidden:
            qs = qs.filter(feature_type__is_visible=True)
        if feature_type_id:
            qs = qs.filter(feature_type__id=feature_type_id)
        if feature_set_id:
            qs = qs.filter(group_temp__id=feature_set_id)

        qs = qs.order_by(self._SORT_FIELD_MAP.get(sort_by, "name"))

        response_data = {
            "features": [
                {
                    "name": feature.name,
                    "type": {"name": feature.feature_type.name, "id": str(feature.feature_type.id)},
                    "description": feature.description or "",
                    "geojson_url": reverse("mapping:mapping-feature-geojson", args=[feature.id.hex]),
                }
                for feature in qs
            ]
        }
        return create_json_response(json.dumps(response_data))


class FeatureGeoJsonView(APIView):
    def get(self, request: Request, id: str) -> HttpResponse:
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
        return create_json_response(feature)


class DeprecatedFeatureListJsonView(DeprecatedEndpointMixin, FeatureListJsonView):
    deprecated_use_instead = "/api/v2.0/features/"


class DeprecatedFeatureGeoJsonView(DeprecatedEndpointMixin, FeatureGeoJsonView):
    deprecated_use_instead = "/api/v2.0/features/<id>/"


class FeatureSetListJsonView(APIView):
    """
    A simple list of featuresets available to the clients
    """

    def get(self, request: Request) -> HttpResponse:
        def feature_types(featureset, include_hidden, summarize_features):
            # First, get all feature types with their counts
            if include_hidden:
                feature_types_qs = featureset.spatialfeaturetype_set.annotate(
                    spatialfeature_count=Count("spatialfeature")
                ).all()
            else:
                feature_types_qs = featureset.spatialfeaturetype_set.annotate(
                    spatialfeature_count=Count("spatialfeature")
                ).filter(is_visible=True)

            # If we need to summarize features, prefetch the related features in a single query
            if summarize_features:
                features_qs = SpatialFeature.objects.filter(feature_type__display_category=featureset)
                if not include_hidden:
                    features_qs = features_qs.filter(feature_type__is_visible=True)

                feature_types_qs = feature_types_qs.prefetch_related(
                    Prefetch("spatialfeature_set", queryset=features_qs, to_attr="prefetched_features")
                )

            for t in feature_types_qs:
                featureTypeDict = {
                    "name": t.name,
                    "id": str(t.id),
                    "feature_count": t.spatialfeature_count,
                }

                if summarize_features:
                    # Use the prefetched features, which are already filtered to this feature type
                    features = getattr(t, "prefetched_features", [])

                    featureTypeDict["feature_summaries"] = [
                        {
                            "name": f.name,
                            "id": str(f.id),  # Convert UUID to string for JSON serialization
                            "bounds": (
                                f.feature_geometry.extent
                                if f.feature_geometry and not f.feature_geometry.empty
                                else None
                            ),
                        }
                        for f in features
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
        return create_json_response(json.dumps(response_data))


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

        return create_json_response(feature)

    def post(self, request, format=None):
        pass


class DeprecatedFeatureSetListJsonView(DeprecatedEndpointMixin, FeatureSetListJsonView):
    deprecated_use_instead = "/displaycategories/"


class DeprecatedFeatureSetGeoJsonView(DeprecatedEndpointMixin, FeatureSetGeoJsonView):
    deprecated_use_instead = "/displaycategories/<id>/"


class MapListJsonView(generics.ListCreateAPIView):
    """
    List of available maps. A Map defines the center location, zoom level and
    tile layers.
    """

    permission_classes = (LayerObjectPermissions,)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.MapWriteSerializer
        return serializers.MapSerializer

    def get_queryset(self):
        return Map.objects.all()


class MapDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (LayerObjectPermissions,)
    lookup_field = "id"

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return serializers.MapWriteSerializer
        return serializers.MapSerializer

    def get_queryset(self):
        return Map.objects.all()


class DeprecatedMapListJsonView(DeprecatedEndpointMixin, MapListJsonView):
    deprecated_use_instead = "/quicklinks/"


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


class DeprecatedLayerListJsonView(DeprecatedEndpointMixin, LayerListJsonView):
    deprecated_use_instead = "/basemaps/"


class DeprecatedLayerJsonView(DeprecatedEndpointMixin, LayerJsonView):
    deprecated_use_instead = "/basemaps/<id>/"


class SpatialFeatureTileView(DRFMVTView):
    """
    Vector tile endpoint for SpatialFeature geometries.

    Returns Mapbox Vector Tiles (MVT) containing spatial features for the given tile coordinates.

    Cache strategy:
    - Server-side TTL ~ 24 hours (spatial features rarely change once stable)
    - Client: 24 hours fresh (max-age), then 3 minutes stale-while-revalidate window
    - Client: stale-if-error for same 24 hour window to mask transient origin faults
    - Authorization: private + Vary so shared caches do not serve one user's tile to another
    """

    layer_classes = [SpatialFeatureLayer]
    permission_classes = (LayerObjectPermissions,)
    content_type = "application/vnd.mapbox-vector-tile"
    schema = CustomSchema()

    # Response varies by auth so shared caches do not serve one user's tile to another
    VARY_HEADER = "Authorization, Cookie"

    # Server-side cache TTL (seconds). Keep a little longer than client max-age so we can
    # usually revalidate from server cache rather than hitting the DB immediately.
    cache_timeout_seconds = 86400  # 1 day server cache
    # Client cache controls (freshness window + stale-while-revalidate window)
    client_max_age_seconds = 86400  # 24 hours fresh
    client_stale_while_revalidate_seconds = 86400  # serve stale up to another 24 hours while revalidating
    client_stale_if_error_seconds = 86400  # serve stale if origin errors for same window

    def get(self, request, z, x, y):
        host = request.get_host().split(":")[0]
        try:
            tenant_data = get_tenant_data_by_host(host)
        except TenantNotFoundException:
            logger.warning("Tenant not found for host %s", host)
            return HttpResponse(status=500)
        if not tenant_data.get("domain"):
            return HttpResponse(status=500)

        # Use class-level ids for cache key so we can avoid instantiating layers on cache hits.
        layer_ids = [lc.id for lc in self.layer_classes]
        try:
            cache_key = build_tile_cache_key(
                request,
                z,
                x,
                y,
                layer_ids,
                cache_version=get_effective_cache_version(),
            )
        except ValueError:
            return HttpResponse(
                status=401, headers={"WWW-Authenticate": "Bearer realm=vector-tiles"}
            )  # Fast reject unauthenticated / malformed token requests

        vt_cache = get_vector_tile_cache()
        # Generate ETag based on cache key for consistent versioning
        # Use SHA256 instead of MD5 for better collision resistance
        etag_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        etag_value = f'"{etag_hash}"'

        # Check if client has current version
        client_etag = request.META.get("HTTP_IF_NONE_MATCH")
        if client_etag == etag_value:
            # Client has current version, send 304
            resp = HttpResponse(status=304)
            resp["ETag"] = etag_value
            resp["Cache-Control"] = (
                "private, max-age="
                f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
                f"stale-if-error={self.client_stale_if_error_seconds}"
            )
            resp["Vary"] = self.VARY_HEADER
            return resp

        cached_payload = vt_cache.get(cache_key)
        if cached_payload is not None:  # Reconstruct fresh response object to avoid mutating cached instance
            content, content_type = cached_payload
            resp = HttpResponse(content, content_type=content_type)
            resp["Cache-Control"] = (
                "private, max-age="
                f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
                f"stale-if-error={self.client_stale_if_error_seconds}"
            )
            resp["ETag"] = etag_value
            resp["Vary"] = self.VARY_HEADER
            resp["X-Cache"] = "HIT"
            return resp
        # Instantiate layers only on a cache miss.
        self.layers = [lc() for lc in self.layer_classes]
        response = self._get(request, z, x, y)

        if response.status_code in (200, 204) and response.get("Content-Type", "").startswith(
            "application/vnd.mapbox-vector-tile"
        ):
            vt_cache.set(
                cache_key, (response.content, response.get("Content-Type")), timeout=self.cache_timeout_seconds
            )
            response["X-Cache"] = "MISS"
        else:
            response["X-Cache"] = "BYPASS"
        response["Cache-Control"] = (
            "private, max-age="
            f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
            f"stale-if-error={self.client_stale_if_error_seconds}"
        )
        response["ETag"] = etag_value
        response["Vary"] = self.VARY_HEADER
        return response

    def _get(self, request, z, x, y, *args, **kwargs):
        """
        Internal method to handle GET request to serve tile, see vectortiles.views.MVTView.get for more details.

        :param request:
        :type request: HttpRequest
        :param x: longitude coordinate tile
        :type x: int
        :param y: latitude coordinate tile
        :type y: int
        :param z: zoom level
        :type z: int

        :rtype HttpResponse
        """
        content, status_code = self.get_content_status(int(z), int(x), int(y))
        return HttpResponse(content, content_type=self.content_type, status=status_code)


class DeprecatedSpatialFeatureTileView(DeprecatedEndpointMixin, SpatialFeatureTileView):
    deprecated_use_instead = "/api/v2.0/features/tiles/<z>/<x>/<y>.pbf"


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
        grid_content = mbtiles.grid(z, x, y, callback)
        return create_json_response(grid_content, content_type="application/javascript; charset=utf8")
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
        return create_json_response(tilejson)
    except MBTilesNotFoundError as e:
        logger.warning(e)
    raise Http404
