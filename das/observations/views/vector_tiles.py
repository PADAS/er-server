import logging

from vectortiles.views import MVTView

from django.http import HttpResponse

from das_server.views import CustomSchema
from mapping.cache import (
    build_tile_cache_key,
    get_effective_cache_version,
    get_vector_tile_cache,
)
from observations.permissions import StandardObjectPermissions
from observations.utils import VIEW_OBSERVATION_PERMS
from observations.vector_layers import ObservationVectorLayer

logger = logging.getLogger(__name__)


class ObservationTileViewSchema(CustomSchema):
    """Schema for observation vector tile endpoint."""

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
                    "description": "Get observations after this ISO8601 date, include timezone",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "until",
                    "in": "query",
                    "description": "Get observations up to this ISO8601 date, include timezone",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "created_after",
                    "in": "query",
                    "description": "Get observations created after this ISO8601 date, include timezone",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "filter",
                    "in": "query",
                    "description": "Filter using exclusion_flags for observations",
                    "schema": {"type": "integer"},
                },
                {
                    "name": "max_time_gap_hours",
                    "in": "query",
                    "description": "Maximum hours between observations for track continuity (default: 24)",
                    "schema": {"type": "number", "default": 24},
                },
                {
                    "name": "speed_threshold_kmh",
                    "in": "query",
                    "description": "Speed threshold in km/h for track segmentation (default: 200)",
                    "schema": {"type": "number", "default": 200},
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class ObservationTileView(MVTView):
    """
    Vector tile endpoint for Observation geometries with track segmentation.

    Returns Mapbox Vector Tiles (MVT) containing observations as points,
    segmented into track collections based on time gaps and speed thresholds.

    Features:
    - Multiple collections within a collection (track segments)
    - Subject filtering by ID(s)
    - Time-based segmentation (max hours between points)
    - Speed-based segmentation (impossible travel speeds)
    - Ordered by recorded_at property

    Cache strategy:
    - Server-side TTL ~ 1 hour (observations change more frequently than spatial features)
    - Client: 5 minutes fresh (max-age), then 5 minutes stale-while-revalidate window
    - Client: stale-if-error for same 5 minute window to mask transient origin faults
    - Authorization varied so per-user/tenant isolation is preserved
    """

    layer_classes = [ObservationVectorLayer]
    permission_classes = (StandardObjectPermissions,)
    content_type = "application/x-protobuf"  # Override vectortiles default content type
    schema = ObservationTileViewSchema()

    # Server-side cache TTL (seconds). Shorter than spatial features since observations change more frequently
    cache_timeout_seconds = 900  # 15 minutes server cache
    # Client cache controls (freshness window + stale-while-revalidate window)
    client_max_age_seconds = 300  # 5 minutes fresh
    client_stale_while_revalidate_seconds = 300  # serve stale up to another 5 minutes while revalidating
    client_stale_if_error_seconds = 300  # serve stale if origin errors for same 5 minutes

    def get(self, request, z, x, y):
        """Handle GET request for vector tiles."""
        # Check permissions
        if not self._check_observation_permissions(request):
            return HttpResponse(status=401, headers={"WWW-Authenticate": "Bearer realm=vector-tiles"})

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
            return HttpResponse(status=401, headers={"WWW-Authenticate": "Bearer realm=vector-tiles"})

        # Check cache
        vector_tile_cache = get_vector_tile_cache()
        cached_payload = vector_tile_cache.get(cache_key)
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

        # Generate new tile
        response = super().get(request, z, x, y)

        # Cache successful responses
        if response.status_code == 200 and response.get("Content-Type", "").startswith("application/x-protobuf"):
            vector_tile_cache.set(
                cache_key, (response.content, response.get("Content-Type")), timeout=self.cache_timeout_seconds
            )
            response["X-Cache"] = "MISS"
        else:
            response["X-Cache"] = "BYPASS"

        # Set cache headers
        response["Cache-Control"] = (
            "public, max-age="
            f"{self.client_max_age_seconds}, stale-while-revalidate={self.client_stale_while_revalidate_seconds}, "
            f"stale-if-error={self.client_stale_if_error_seconds}"
        )
        response["Vary"] = "Authorization"
        return response

    def _check_observation_permissions(self, request):
        """Check if user has permission to view observations."""
        try:
            return request.user.has_any_perms(VIEW_OBSERVATION_PERMS)
        except Exception as e:
            logger.warning(f"Error checking observation permissions: {e}")
            return False
