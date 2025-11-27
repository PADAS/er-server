import hashlib
import logging

from vectortiles.views import MVTView

from django.http import HttpResponse

from das_server.views import CustomSchema
from mapping.cache import (
    build_tile_cache_key,
    get_effective_cache_version,
    get_vector_tile_cache,
)
from observations.permissions import SubjectModelPermissions
from observations.utils import VIEW_OBSERVATION_PERMS
from observations.vector_layers_segments import ObservationSegmentVectorLayer
from utils.tenant.providers import get_tenant_data_by_host

logger = logging.getLogger(__name__)


class ObservationSegmentTileViewSchema(CustomSchema):
    """Schema for observation segment vector tile endpoint."""

    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "subject_id",
                    "in": "query",
                    "description": "Filter to a single subject by ID",
                    "schema": {"type": "string", "format": "uuid"},
                },
                {
                    "name": "subject_ids",
                    "in": "query",
                    "description": "Filter to multiple subjects by ID (comma-separated)",
                    "schema": {"type": "string"},
                },
                {
                    "name": "since",
                    "in": "query",
                    "description": "Get segments after this ISO8601 date, include timezone",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "until",
                    "in": "query",
                    "description": "Get segments up to this ISO8601 date, include timezone",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "created_after",
                    "in": "query",
                    "description": "Get segments created after this ISO8601 date, include timezone",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "filter",
                    "in": "query",
                    "description": "Filter using exclusion_flags for segments",
                    "schema": {"type": "integer"},
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class ObservationSegmentTileView(MVTView):
    """
    Vector tile endpoint for pre-computed ObservationSegment geometries.

    Returns Mapbox Vector Tiles (MVT) containing track segments as LineString features.
    Each segment represents the line between two consecutive observations with
    computed metrics (speed, time gap, distance).

    Features:
    - Subject filtering by ID(s)
    - Time-based filtering (since/until on segment start time)
    - Exclusion flag filtering
    - Ordered by start_recorded_at

    Cache strategy:
    - Server-side TTL ~ 15 minutes (segments update when observations change)
    - Client: 5 minutes fresh (max-age), then 5 minutes stale-while-revalidate window
    - Client: stale-if-error for same 5 minute window to mask transient origin faults
    - Authorization varied so per-user/tenant isolation is preserved
    """

    layer_classes = [ObservationSegmentVectorLayer]
    permission_classes = (SubjectModelPermissions,)
    content_type = "application/vnd.mapbox-vector-tile"
    schema = ObservationSegmentTileViewSchema()

    # Server-side cache TTL (seconds)
    cache_timeout_seconds = 900  # 15 minutes server cache
    # Client cache controls (freshness window + stale-while-revalidate window)
    client_max_age_seconds = 300  # 5 minutes fresh
    client_stale_while_revalidate_seconds = 300  # serve stale up to another 5 minutes while revalidating
    client_stale_if_error_seconds = 300  # serve stale if origin errors for same 5 minutes

    def get(self, request, z, x, y):
        """
        Handle GET request for vector tiles.
        Implements tenant validation, permission checks, caching, and error handling.
        """
        host = request.get_host().split(":")[0]
        try:
            tenant_data = get_tenant_data_by_host(host)
        except Exception as e:
            logger.error(f"Tenant data fetch error: {e}")
            return HttpResponse("Tenant data error", status=500)
        if not tenant_data.get("domain"):
            logger.error(f"Missing tenant domain for host: {host}")
            return HttpResponse("Missing tenant domain", status=500)

        if not self._check_observation_permissions(request):
            logger.warning(f"Permission denied for user {getattr(request.user, 'id', None)}")
            return HttpResponse(
                "Permission denied", status=401, headers={"WWW-Authenticate": "Bearer realm=vector-tiles"}
            )

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
        except ValueError as e:
            logger.warning(f"Cache key build error: {e}")
            return HttpResponse(
                "Malformed token or unauthenticated request",
                status=401,
                headers={"WWW-Authenticate": "Bearer realm=vector-tiles"},
            )

        vt_cache = get_vector_tile_cache()
        etag_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        etag_value = f'"{etag_hash}"'

        client_etag = request.META.get("HTTP_IF_NONE_MATCH")
        if client_etag == etag_value:
            resp = HttpResponse(status=304)
            resp["ETag"] = etag_value
            resp["Cache-Control"] = (
                "public, max-age="
                f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
                f"stale-if-error={self.client_stale_if_error_seconds}"
            )
            return resp

        cached_payload = vt_cache.get(cache_key)
        if cached_payload is not None:
            content, content_type = cached_payload
            resp = HttpResponse(content, content_type=content_type)
            resp["Cache-Control"] = (
                "public, max-age="
                f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
                f"stale-if-error={self.client_stale_if_error_seconds}"
            )
            resp["ETag"] = etag_value
            resp["X-Cache"] = "HIT"
            return resp

        self.layers = [lc() for lc in self.layer_classes]
        response = super().get(request, z, x, y)
        if response.status_code == 200 and response.get("Content-Type", "").startswith("application/x-protobuf"):
            vt_cache.set(
                cache_key, (response.content, response.get("Content-Type")), timeout=self.cache_timeout_seconds
            )
            response["X-Cache"] = "MISS"
        else:
            response["X-Cache"] = "BYPASS"
        response["Cache-Control"] = (
            "public, max-age="
            f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
            f"stale-if-error={self.client_stale_if_error_seconds}"
        )
        response["ETag"] = etag_value
        return response

    def _check_observation_permissions(self, request):
        """Check if user has permission to view observations."""
        try:
            return request.user.has_any_perms(VIEW_OBSERVATION_PERMS)
        except Exception as e:
            logger.warning(f"Error checking observation permissions: {e}")
            return False
