import hashlib
import logging

from django.http import HttpResponse
from rest_framework.permissions import BasePermission

from das_server.views import CustomSchema, DRFMVTView
from observations.models import Subject
from observations.permissions import SubjectModelPermissions
from observations.utils import VIEW_OBSERVATION_PERMS
from observations.vector_layers import ObservationSegmentVectorLayer, SubjectVectorLayer
from utils.cache import (
    build_tile_cache_key,
    get_effective_cache_version,
    get_vector_tile_cache,
)
from utils.tenant.providers import get_tenant_data_by_host

logger = logging.getLogger(__name__)


class ObservationSegmentTilePermission(BasePermission):
    """
    Allow access only when request host resolves to a valid tenant and user
    has permission to view observations. Used so permission_classes on the
    tile view are enforced (tenant + observation view perm).
    """

    def has_permission(self, request, view):
        host = request.get_host().split(":")[0]
        try:
            tenant_data = get_tenant_data_by_host(host)
        except Exception as e:
            logger.warning("Tenant data fetch error: %s", e)
            return False
        if not tenant_data.get("domain"):
            logger.warning("Missing tenant domain for host: %s", host)
            return False
        try:
            return request.user.has_any_perms(VIEW_OBSERVATION_PERMS)
        except Exception as e:
            logger.warning("Error checking observation permissions: %s", e)
            return False


class ObservationSegmentTileViewSchema(CustomSchema):
    """Schema for observation segment vector tile endpoint."""

    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "range",
                    "in": "query",
                    "description": "Time range: '45' (segments that ended in the last 45 days, default) or 'all'",
                    "schema": {"type": "string", "enum": ["45", "all"]},
                },
                {
                    "name": "show_excluded",
                    "in": "query",
                    "description": "Include segments with truthy exclusion flags (default: excluded)",
                    "schema": {"type": "boolean"},
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class ObservationSegmentTileView(DRFMVTView):
    """
    Vector tile endpoint for pre-computed ObservationSegment geometries.

    Returns Mapbox Vector Tiles (MVT) containing track segments as LineString features.
    Each segment represents the line between two consecutive observations with
    computed metrics (speed, time gap, distance).

    Features:
    - range: "45" (default) limits to segments that ended in the last 45 days; "all" for no limit
    - show_excluded: include segments with truthy exclusion flags when true (default: excluded)
    - Ordered by start_recorded_at

    Cache strategy:
    - Server-side TTL ~ 15 minutes (segments update when observations change)
    - Client: 5 minutes fresh (max-age), then 5 minutes stale-while-revalidate window
    - Client: stale-if-error for same 5 minute window to mask transient origin faults
    - Authorization: private + Vary so shared caches do not serve one user's tile to another
    """

    layer_classes = [ObservationSegmentVectorLayer, SubjectVectorLayer]
    permission_classes = (SubjectModelPermissions, ObservationSegmentTilePermission)
    content_type = "application/vnd.mapbox-vector-tile"
    schema = ObservationSegmentTileViewSchema()

    # Server-side cache TTL (seconds)
    cache_timeout_seconds = 900  # 15 minutes server cache
    # Client cache controls (freshness window + stale-while-revalidate window)
    # Note: Real-time subject positions are handled via GeoJSON + WebSocket, so these tiles
    # are primarily for efficient bulk rendering, not the source of truth for freshness
    client_max_age_seconds = 300  # 5 minutes fresh
    client_stale_while_revalidate_seconds = 300  # serve stale up to another 5 minutes while revalidating
    client_stale_if_error_seconds = 300  # serve stale if origin errors for same 5 minutes

    # Response varies by auth so shared caches do not serve one user's tile to another
    VARY_HEADER = "Authorization, Cookie"

    def get_queryset(self):
        """Return a queryset for DRF permission classes (SubjectModelPermissions needs a model).
        This view serves tiles from layer_classes, not from a single queryset.
        """
        return Subject.objects.none()

    def get(self, request, z, x, y):
        """
        Handle GET request for vector tiles.
        Implements tile validation, caching, and error handling.
        Authentication, tenant validity, and observation view permission
        are enforced by permission_classes (SubjectModelPermissions,
        ObservationSegmentTilePermission).
        """
        # Validate tile coordinates: z in 0-24, x/y within valid range for zoom
        try:
            z = int(z)
            x = int(x)
            y = int(y)
        except (TypeError, ValueError):
            return HttpResponse("Invalid tile coordinates", status=400)
        if z < 0 or z > 24:
            return HttpResponse("Invalid zoom level", status=400)
        max_tile = (1 << z) - 1
        if x < 0 or x > max_tile or y < 0 or y > max_tile:
            return HttpResponse("Tile out of range for zoom level", status=400)

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
                status=403,
                headers={"WWW-Authenticate": "Bearer realm=vector-tiles"},
            )

        vt_cache = get_vector_tile_cache()
        etag_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        etag_value = f'"{etag_hash}"'
        cache_control_value = (
            f"private, max-age={self.client_max_age_seconds}, "
            f"stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
            f"stale-if-error={self.client_stale_if_error_seconds}"
        )

        # Check server cache FIRST.  Signal handlers delete entries on data
        # change, so a miss means the tile may be stale — skip the ETag
        # shortcut and regenerate.  Only return 304 when the entry still exists.
        cached_payload = vt_cache.get(cache_key)
        if cached_payload is not None:
            client_etag = request.META.get("HTTP_IF_NONE_MATCH")
            if client_etag == etag_value:
                resp = HttpResponse(status=304)
                resp["ETag"] = etag_value
                resp["Cache-Control"] = cache_control_value
                resp["Vary"] = self.VARY_HEADER
                return resp

            content, content_type = cached_payload
            resp = HttpResponse(content, content_type=content_type)
            resp["Cache-Control"] = cache_control_value
            resp["ETag"] = etag_value
            resp["Vary"] = self.VARY_HEADER
            resp["X-Cache"] = "HIT"
            return resp

        # Cache miss — regenerate tile from the database.
        self.layers = [lc(request=request) for lc in self.layer_classes]
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
        response["Cache-Control"] = cache_control_value
        response["ETag"] = etag_value
        response["Vary"] = self.VARY_HEADER
        return response

    def _get(self, request, z, x, y, *args, **kwargs):
        """Serve tile content; used after cache miss. See vectortiles mixins get_content_status."""
        content, status = self.get_content_status(int(z), int(x), int(y))
        return HttpResponse(content, content_type=self.content_type, status=status)
