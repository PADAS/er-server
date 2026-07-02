"""Mapbox Vector Tile endpoint for Events.

Serves events as MVT (binary PBF) generated in PostGIS via ``ST_AsMVT``, with
full ``/activity/events`` filter parity (the same DRF filter backends run inside
``EventVectorLayer``), a short-TTL per-user Redis cache, and per-user /
per-tenant cache-busting via version counters in ``utils.cache``.

Modeled on ``observations.views.vector_tiles_segments.ObservationSegmentTileView``.
"""

from __future__ import annotations

import hashlib
import logging

from django.http import HttpResponse
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from activity.models import Event
from activity.permissions import EventsPermissions
from activity.tile_cache import get_event_tile_cache_version
from activity.vector_layers import (
    EventGeometryCentroidVectorLayer,
    EventGeometryVectorLayer,
    EventVectorLayer,
)
from das_server.views import CustomSchema, DRFMVTView
from utils.cache import build_tile_cache_key, get_vector_tile_cache
from utils.tenant.providers import get_tenant_data_by_host

logger = logging.getLogger(__name__)


class EventTileTenantPermission(BasePermission):
    """Allow access only when the request host resolves to a valid tenant.

    Category/geo read scoping is enforced inside ``EventVectorLayer`` (it reuses
    ``EventPermissionsFilter``), so this guard only validates host -> tenant and
    that the user is authenticated. Mirrors ``ObservationSegmentTilePermission``.
    """

    def has_permission(self, request: Request, view: object) -> bool:
        host = request.get_host().split(":")[0]
        try:
            tenant_data = get_tenant_data_by_host(host)
        except Exception as e:
            logger.warning("Tenant data fetch error: %s", e)
            return False
        if not tenant_data.get("domain"):
            logger.warning("Missing tenant domain for host: %s", host)
            return False
        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated)


class EventTileViewSchema(CustomSchema):
    """OpenAPI schema for the events vector tile endpoint."""

    def get_operation(self, *args: object, **kwargs: object) -> dict:
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "event_type",
                    "in": "query",
                    "description": "Restrict to events with these event-type ids (repeatable).",
                    "schema": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                },
                {
                    "name": "event_category",
                    "in": "query",
                    "description": "Restrict to events in these category values (repeatable). Also scopes read perms.",
                    "schema": {"type": "array", "items": {"type": "string"}},
                },
                {
                    "name": "state",
                    "in": "query",
                    "description": "Restrict to events in these states, e.g. new/active/resolved (repeatable).",
                    "schema": {"type": "array", "items": {"type": "string"}},
                },
                {
                    "name": "event_ids",
                    "in": "query",
                    "description": "Restrict to these event ids (repeatable).",
                    "schema": {"type": "array", "items": {"type": "string", "format": "uuid"}},
                },
                {
                    "name": "updated_since",
                    "in": "query",
                    "description": "Only events updated at or after this ISO-8601 timestamp.",
                    "schema": {"type": "string", "format": "date-time"},
                },
                {
                    "name": "is_collection",
                    "in": "query",
                    "description": "Filter by event-type is_collection (mutually exclusive with exclude_contained).",
                    "schema": {"type": "boolean"},
                },
                {
                    "name": "exclude_contained",
                    "in": "query",
                    "description": "Exclude events contained by a collection (mutually exclusive with is_collection).",
                    "schema": {"type": "boolean"},
                },
                {
                    "name": "bbox",
                    "in": "query",
                    "description": "Bounding box 'west,south,east,north' (lon,lat).",
                    "schema": {"type": "string"},
                },
                {
                    "name": "filter",
                    "in": "query",
                    "description": "URL-encoded JSON event filter spec (text, date_range, priority, state, ...).",
                    "schema": {"type": "string"},
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class EventTileView(DRFMVTView):
    """Vector tile endpoint for Events as Point features (MVT / PBF).

    Honors the full ``/activity/events`` filter surface (the same filter backends
    run inside ``EventVectorLayer``) plus category/geo permission and
    related-subject scoping.

    Cache strategy:
    - Server-side Redis TTL of 5 min; cache key includes a per-user version
      counter (bumped on token-delete / permission change) and a per-tenant event
      data version (bumped on event update/delete). Creates rely on the realtime
      socket + TTL expiry, not on a tile bump.
    - Client: ~3 min fresh (max-age), then stale-while-revalidate / stale-if-error.
    - Authorization: private + Vary so shared caches do not serve one user's tile
      to another.

    ``layer_classes`` is a list to leave the door open to a multi-class layer
    (events + subjects) without rewriting the view.
    """

    layer_classes = [EventVectorLayer, EventGeometryVectorLayer, EventGeometryCentroidVectorLayer]
    permission_classes = (EventsPermissions, EventTileTenantPermission)
    content_type = "application/vnd.mapbox-vector-tile"
    schema = EventTileViewSchema()

    # Server-side cache TTL (seconds) — ticket: very short (3-5 min).
    cache_timeout_seconds = 300  # 5 minutes
    # Client cache controls (freshness + stale windows).
    client_max_age_seconds = 180  # 3 minutes fresh
    client_stale_while_revalidate_seconds = 300
    client_stale_if_error_seconds = 300

    VARY_HEADER = "Authorization, Cookie"

    def get_queryset(self):
        """Return an empty queryset for DRF machinery.

        Tiles are served from ``layer_classes``, not from a single view queryset.
        """
        return Event.objects.none()

    def get(self, request: Request, z: int, x: int, y: int) -> HttpResponse:
        """Serve a single event vector tile.

        Authentication, tenant validity, and event read scoping are enforced by
        ``permission_classes`` + the filter backends inside ``EventVectorLayer``.
        Invalid filter params raised by those backends (``ParseError`` /
        ``BadRequestAPIException``) propagate to DRF -> 400.
        """
        # Validate tile coordinates: z in 0-24, x/y within valid range for zoom.
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
            tenant_id = str(request.user.das_tenant_id)
            user_id = str(request.user.id)
            cache_key = build_tile_cache_key(
                request,
                z,
                x,
                y,
                layer_ids,
                cache_version=get_event_tile_cache_version(tenant_id, user_id),
            )
        except (ValueError, AttributeError) as e:
            logger.warning("Cache key build error: %s", e)
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

    def _get(self, request: Request, z: int, x: int, y: int, *args: object, **kwargs: object) -> HttpResponse:
        """Serve tile content after a cache miss (see vectortiles ``get_content_status``)."""
        content, status = self.get_content_status(int(z), int(x), int(y))
        return HttpResponse(content, content_type=self.content_type, status=status)
