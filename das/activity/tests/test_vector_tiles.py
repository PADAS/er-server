"""Tests for the Events vector tile endpoint (ERA-11809).

Mirrors ``observations/tests/test_vector_tiles.py``:
- layer config + queryset-level filter/permission parity with ``/activity/events``
- view-level response (status, content-type, cache headers)
- binary MVT decode (when ``mapbox_vector_tile`` is installed) to assert the tile
  carries the expected events and ``tile_fields``
- per-user / per-tenant cache HIT/MISS + ETag 304 + busting
"""

from __future__ import annotations

import re

import pytest

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point, Polygon
from django.core.cache import caches
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from accounts.models.permissionset import PermissionSet
from accounts.tile_cache import bump_user_tile_version
from activity.models import Event, EventCategory, EventGeometry, EventType
from activity.tile_cache import (
    bump_event_tile_data_version,
    get_event_tile_cache_version,
)
from activity.vector_layers import (
    EventGeometryCentroidVectorLayer,
    EventGeometryVectorLayer,
    EventVectorLayer,
)
from activity.views.events.vector_tiles import EventTileView

TILE_URL_NAME = "event-tiles"
# Tile (z=3, x=4, y=2) spans lon [0, 45], lat [~41, ~66.5]; min_zoom is 3 so we
# must request z >= 3. EVENT_LON/LAT sits comfortably inside that tile so the
# event appears in the rendered MVT.
Z, X, Y = 3, 4, 2
EVENT_LON, EVENT_LAT = 22.5, 53.0


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #


def _tile_url(z: int = Z, x: int = X, y: int = Y) -> str:
    return reverse(TILE_URL_NAME, kwargs={"z": z, "x": x, "y": y})


def _grant_category_read(user, category_value: str) -> PermissionSet:
    """Grant ``{category}_read`` to a user via a fresh permission set.

    Category permissions are created by the EventCategory post_save signal with a
    tenant-prefixed codename (``{short_tenant}:{category}_read``); match on the
    bare suffix so we don't depend on the prefix form.
    """
    perm = Permission.objects.filter(
        codename__endswith=f"{category_value}_read",
        content_type__app_label="activity",
        content_type__model="event",
    ).first()
    assert perm is not None, f"expected a '{category_value}_read' event permission to exist"
    perm_set = PermissionSet.objects.create(name=f"{category_value}_read_set_{user.id}", das_tenant=user.das_tenant)
    perm_set.permissions.add(perm)
    user.permission_sets.add(perm_set)
    # Clear cached permission lookups so has_perm sees the new grant.
    for attr in ("_group_perm_cache", "_perm_cache"):
        if getattr(user, attr, None) is not None:
            delattr(user, attr)
    return perm_set


@pytest.fixture
def patch_tile_tenant(monkeypatch, das_tenant):
    """Stub tenant resolution so the tile view accepts requests in tests."""
    monkeypatch.setattr(
        "activity.views.events.vector_tiles.get_tenant_data_by_host",
        lambda host: {"domain": das_tenant.domain},
    )


@pytest.fixture
def security_category(das_tenant) -> EventCategory:
    return EventCategory.objects.create(value="security", display="Security", das_tenant=das_tenant)


@pytest.fixture
def monitoring_category(das_tenant) -> EventCategory:
    return EventCategory.objects.create(value="monitoring", display="Monitoring", das_tenant=das_tenant)


@pytest.fixture
def security_event_type(das_tenant, security_category) -> EventType:
    return EventType.objects.create(value="fire", display="Fire", category=security_category, das_tenant=das_tenant)


@pytest.fixture
def monitoring_event_type(das_tenant, monitoring_category) -> EventType:
    return EventType.objects.create(
        value="sighting", display="Sighting", category=monitoring_category, das_tenant=das_tenant
    )


@pytest.fixture
def located_event(das_tenant, security_event_type) -> Event:
    return Event.objects.create(
        title="Located Security Event",
        event_type=security_event_type,
        location=Point(EVENT_LON, EVENT_LAT, srid=4326),
        priority=Event.PRI_URGENT,
        state=Event.SC_NEW,
        das_tenant=das_tenant,
    )


def _polygon_around(lon: float, lat: float, half: float = 1.0) -> Polygon:
    """A small square polygon centered on ``(lon, lat)`` in WGS84."""
    return Polygon(
        (
            (lon - half, lat - half),
            (lon - half, lat + half),
            (lon + half, lat + half),
            (lon + half, lat - half),
            (lon - half, lat - half),
        ),
        srid=4326,
    )


@pytest.fixture
def polygon_only_event(das_tenant, security_event_type) -> Event:
    """An Event with no point ``location`` but one ``EventGeometry`` polygon.

    The polygon is centered on EVENT_LON/EVENT_LAT so it falls inside the same
    test tile the point tests use.
    """
    event = Event.objects.create(
        title="Polygon Only Security Event",
        event_type=security_event_type,
        location=None,
        priority=Event.PRI_URGENT,
        state=Event.SC_NEW,
        das_tenant=das_tenant,
    )
    EventGeometry.objects.create(
        event=event,
        geometry=_polygon_around(EVENT_LON, EVENT_LAT),
        das_tenant=das_tenant,
    )
    return event


def _request_for(user, url: str | None = None) -> Request:
    """Build a DRF Request (events filter backends read ``request.query_params``)."""
    drf_request = Request(APIRequestFactory().get(url or _tile_url()))
    drf_request.user = user
    return drf_request


# --------------------------------------------------------------------------- #
# Layer configuration + queryset
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventVectorLayerConfig:
    def test_layer_configuration(self):
        layer = EventVectorLayer()
        assert layer.id == "events"
        assert layer.model is Event
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24
        for field in ("id", "serial_number", "event_type_value", "event_category", "color", "image"):
            assert field in layer.tile_fields

    def test_queryset_excludes_events_without_location(self, das_tenant, security_event_type):
        Event.objects.create(title="No Location", event_type=security_event_type, das_tenant=das_tenant)
        layer = EventVectorLayer()
        assert layer.get_queryset().count() == 0

    def test_queryset_includes_located_event_with_geom_in_web_mercator(self, located_event):
        layer = EventVectorLayer()
        obj = layer.get_queryset().filter(id=located_event.id).first()
        assert obj is not None
        assert obj.geom is not None
        assert obj.geom.srid == 3857

    def test_queryset_annotates_tile_fields(self, located_event):
        layer = EventVectorLayer()
        obj = layer.get_queryset().filter(id=located_event.id).first()
        assert obj.event_type_value == "fire"
        assert obj.event_category == "security"
        # Urgent (300) + new -> red icon basename.
        assert obj.color == "red"
        assert obj.image == "/static/sprite-src/fire-red.svg"
        assert obj.event_time_iso.endswith("Z")
        assert obj.updated_at_iso.endswith("Z")

    def test_queryset_annotates_epoch_millis_fields(self, located_event):
        layer = EventVectorLayer()
        obj = layer.get_queryset().filter(id=located_event.id).first()

        assert isinstance(obj.event_time_ms, int)
        assert isinstance(obj.updated_at_ms, int)

        # SQL uses floor(extract(epoch from ...) * 1000)::bigint; mirror that
        # with int() which truncates (identical to floor for positive values).
        expected_event_time_ms = int(located_event.event_time.timestamp() * 1000)
        # updated_at is set by the DB on creation; re-fetch to get the exact value.
        located_event.refresh_from_db()
        expected_updated_at_ms = int(located_event.updated_at.timestamp() * 1000)

        assert abs(obj.event_time_ms - expected_event_time_ms) <= 1
        assert abs(obj.updated_at_ms - expected_updated_at_ms) <= 1

    def test_tile_fields_includes_epoch_millis_fields(self):
        layer = EventVectorLayer()
        assert "event_time_ms" in layer.tile_fields
        assert "updated_at_ms" in layer.tile_fields

    def test_tile_fields_includes_event_time_display(self):
        layer = EventVectorLayer()
        assert "event_time_display" in layer.tile_fields

    def test_queryset_annotates_display_timestamp(self, located_event):
        layer = EventVectorLayer()
        obj = layer.get_queryset().filter(id=located_event.id).first()

        assert isinstance(obj.event_time_display, str)
        assert re.fullmatch(
            r"[A-Z][a-z]{2} \d{2}, \d{2}:\d{2} UTC", obj.event_time_display
        ), f"event_time_display {obj.event_time_display!r} does not match expected format"

        # Secondary: verify the value matches the Python-formatted equivalent.
        from datetime import timezone

        event_time_utc = located_event.event_time.astimezone(timezone.utc)
        expected = event_time_utc.strftime("%b %d, %H:%M UTC")
        assert (
            obj.event_time_display == expected
        ), f"event_time_display {obj.event_time_display!r} != expected {expected!r}"

    def test_resolved_event_uses_lt_gray_color(self, das_tenant, security_event_type):
        event = Event.objects.create(
            title="Resolved",
            event_type=security_event_type,
            location=Point(0.0, 0.0, srid=4326),
            priority=Event.PRI_URGENT,
            state=Event.SC_RESOLVED,
            das_tenant=das_tenant,
        )
        layer = EventVectorLayer()
        obj = layer.get_queryset().filter(id=event.id).first()
        assert obj.color == "lt_gray"
        assert obj.image == "/static/sprite-src/fire-lt_gray.svg"

    @pytest.mark.parametrize(
        "priority,expected_color",
        [
            (Event.PRI_NONE, "gray"),
            (Event.PRI_REFERENCE, "med_green"),
            (Event.PRI_IMPORTANT, "amber"),
            (Event.PRI_URGENT, "red"),
        ],
    )
    def test_priority_color_mapping(self, das_tenant, security_event_type, priority, expected_color):
        event = Event.objects.create(
            title="Prio",
            event_type=security_event_type,
            location=Point(0.0, 0.0, srid=4326),
            priority=priority,
            state=Event.SC_NEW,
            das_tenant=das_tenant,
        )
        obj = EventVectorLayer().get_queryset().filter(id=event.id).first()
        assert obj.color == expected_color


# --------------------------------------------------------------------------- #
# Filter parity with /activity/events
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventVectorLayerFilterParity:
    def test_state_filter(self, das_tenant, superuser, security_event_type):
        new_event = Event.objects.create(
            title="New",
            event_type=security_event_type,
            location=Point(0, 0, srid=4326),
            state=Event.SC_NEW,
            das_tenant=das_tenant,
        )
        Event.objects.create(
            title="Resolved",
            event_type=security_event_type,
            location=Point(0, 0, srid=4326),
            state=Event.SC_RESOLVED,
            das_tenant=das_tenant,
        )
        request = _request_for(superuser, _tile_url() + "?state=new")
        ids = set(EventVectorLayer(request=request).get_queryset().values_list("id", flat=True))
        assert ids == {new_event.id}

    def test_event_type_filter(self, das_tenant, superuser, security_event_type, monitoring_event_type):
        fire = Event.objects.create(
            title="Fire",
            event_type=security_event_type,
            location=Point(0, 0, srid=4326),
            das_tenant=das_tenant,
        )
        Event.objects.create(
            title="Sighting",
            event_type=monitoring_event_type,
            location=Point(0, 0, srid=4326),
            das_tenant=das_tenant,
        )
        # The events API's event_type param filters on the FK id (UUID), matching
        # EventListFilter.by_event_type / EventFilteringQuerySet.by_event_type.
        request = _request_for(superuser, _tile_url() + f"?event_type={security_event_type.id}")
        ids = set(EventVectorLayer(request=request).get_queryset().values_list("id", flat=True))
        assert ids == {fire.id}

    def test_bbox_filter(self, das_tenant, superuser, security_event_type):
        inside = Event.objects.create(
            title="Inside",
            event_type=security_event_type,
            location=Point(0.0, 0.0, srid=4326),
            das_tenant=das_tenant,
        )
        Event.objects.create(
            title="Outside",
            event_type=security_event_type,
            location=Point(50.0, 50.0, srid=4326),
            das_tenant=das_tenant,
        )
        request = _request_for(superuser, _tile_url() + "?bbox=-1,-1,1,1")
        ids = set(EventVectorLayer(request=request).get_queryset().values_list("id", flat=True))
        assert ids == {inside.id}

    def test_json_filter_priority(self, das_tenant, superuser, security_event_type):
        urgent = Event.objects.create(
            title="Urgent",
            event_type=security_event_type,
            location=Point(0, 0, srid=4326),
            priority=Event.PRI_URGENT,
            das_tenant=das_tenant,
        )
        Event.objects.create(
            title="None",
            event_type=security_event_type,
            location=Point(0, 0, srid=4326),
            priority=Event.PRI_NONE,
            das_tenant=das_tenant,
        )
        request = _request_for(superuser, _tile_url() + '?filter={"priority": [300]}')
        ids = set(EventVectorLayer(request=request).get_queryset().values_list("id", flat=True))
        assert ids == {urgent.id}


# --------------------------------------------------------------------------- #
# Permissions / tenant isolation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventVectorLayerPermissions:
    def test_user_without_category_perm_sees_no_events(self, user, located_event):
        request = _request_for(user)
        assert EventVectorLayer(request=request).get_queryset().count() == 0

    def test_user_with_category_perm_sees_events_in_that_category(
        self, user, located_event, monitoring_event_type, das_tenant
    ):
        denied = Event.objects.create(
            title="Monitoring",
            event_type=monitoring_event_type,
            location=Point(0, 0, srid=4326),
            das_tenant=das_tenant,
        )
        _grant_category_read(user, "security")
        request = _request_for(user)
        ids = set(EventVectorLayer(request=request).get_queryset().values_list("id", flat=True))
        assert located_event.id in ids
        assert denied.id not in ids

    def test_no_request_returns_all_located_events(self, located_event):
        # No request -> no permission filtering (current-tenant scoped).
        ids = set(EventVectorLayer().get_queryset().values_list("id", flat=True))
        assert located_event.id in ids


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventVectorLayerTenantIsolation:
    """Events from another tenant must never leak into the tile queryset.

    Follows the cross-tenant pattern in ``test_patrol_filtering_queryset``:
    ``das_tenant_monkeypatch`` pins the current tenant via the mocked
    ``django_multitenant.utils._context``; we flip it only to build the
    other-tenant rows, then assert the current-tenant layer query excludes them.
    """

    def test_other_tenant_events_do_not_leak(self, das_tenant, security_event_type, located_event):
        import django_multitenant.utils

        from django.db.models.signals import post_save

        from activity.signals import ensure_perms_exist
        from factories import TenantFactory

        # Explicit distinct id/domain — TenantFactory defaults to the shared test
        # tenant id, which would collide with das_tenant and defeat the test.
        other_tenant = TenantFactory.create(id="11111111-1111-1111-1111-111111111111", domain="other.example.com")

        previous = django_multitenant.utils._context.tenant
        # The EventCategory post_save perms signal needs thread tenant settings,
        # which point at the current (pinned) tenant; silence it while we build
        # the other-tenant rows. The layer applies no request -> no perm filter.
        post_save.disconnect(ensure_perms_exist, sender=EventCategory)
        django_multitenant.utils._context.tenant = other_tenant
        try:
            other_cat = EventCategory.objects.create(value="iso_other", display="Other", das_tenant=other_tenant)
            other_et = EventType.objects.create(
                value="iso_other", display="Other", category=other_cat, das_tenant=other_tenant
            )
            other_event = Event.objects.create(
                title="Other tenant event",
                event_type=other_et,
                location=Point(EVENT_LON, EVENT_LAT, srid=4326),
                das_tenant=other_tenant,
            )
        finally:
            django_multitenant.utils._context.tenant = previous
            post_save.connect(ensure_perms_exist, sender=EventCategory)

        ids = set(EventVectorLayer().get_queryset().values_list("id", flat=True))
        assert located_event.id in ids
        assert other_event.id not in ids, "another tenant's event must not leak into the current tenant tile query"


# --------------------------------------------------------------------------- #
# View: response, caching, busting
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventTileView:
    def _get(self, user, url: str | None = None, **headers):
        request = APIRequestFactory().get(url or _tile_url(), **headers)
        request.user = user
        return EventTileView.as_view()(request, Z, X, Y)

    def test_returns_mvt_content_type(self, superuser, located_event, patch_tile_tenant):
        response = self._get(superuser)
        assert response.status_code in (200, 204)
        assert response["Content-Type"] == "application/vnd.mapbox-vector-tile"

    def test_cache_headers_present(self, superuser, located_event, patch_tile_tenant):
        response = self._get(superuser)
        assert response["Cache-Control"].startswith("private")
        assert "max-age" in response["Cache-Control"]
        assert "ETag" in response
        assert "X-Cache" in response
        vary = response.get("Vary", "")
        assert "Authorization" in vary and "Cookie" in vary

    def test_cache_miss_then_hit(self, superuser, located_event, patch_tile_tenant):
        first = self._get(superuser)
        assert first["X-Cache"] == "MISS"
        second = self._get(superuser)
        assert second["X-Cache"] == "HIT"

    def test_etag_304(self, superuser, located_event, patch_tile_tenant):
        first = self._get(superuser)  # populate cache
        etag = first["ETag"]
        second = self._get(superuser, HTTP_IF_NONE_MATCH=etag)
        assert second.status_code == 304

    def test_cache_key_varies_by_query_string(self, superuser, located_event, patch_tile_tenant):
        r1 = self._get(superuser, _tile_url() + "?state=new")
        r2 = self._get(superuser, _tile_url() + "?state=resolved")
        assert r1["ETag"] != r2["ETag"]

    def test_cache_key_varies_by_user(self, superuser, create_user, located_event, patch_tile_tenant):
        other = create_user(is_superuser=True, username="other_super")
        r1 = self._get(superuser)
        r2 = self._get(other)
        assert r1["ETag"] != r2["ETag"]

    def test_invalid_bbox_returns_400(self, superuser, located_event, patch_tile_tenant):
        response = self._get(superuser, _tile_url() + "?bbox=notanumber")
        assert response.status_code == 400

    def test_invalid_json_filter_returns_400(self, superuser, located_event, patch_tile_tenant):
        response = self._get(superuser, _tile_url() + "?filter={bad json")
        assert response.status_code == 400

    def test_bad_tile_coordinates_return_400(self, superuser, located_event, patch_tile_tenant):
        request = APIRequestFactory().get("/activity/events/tiles/2/99/99.pbf")
        request.user = superuser
        response = EventTileView.as_view()(request, 2, 99, 99)
        assert response.status_code == 400

    def test_invalid_zoom_returns_400(self, superuser, located_event, patch_tile_tenant):
        request = APIRequestFactory().get("/activity/events/tiles/99/0/0.pbf")
        request.user = superuser
        response = EventTileView.as_view()(request, 99, 0, 0)
        assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventTileCacheBusting:
    def _get(self, user):
        request = APIRequestFactory().get(_tile_url())
        request.user = user
        return EventTileView.as_view()(request, Z, X, Y)

    def test_bump_user_version_busts_only_that_user(self, superuser, create_user, located_event, patch_tile_tenant):
        other = create_user(is_superuser=True, username="other_super_bust")

        # Prime both users' caches.
        assert self._get(superuser)["X-Cache"] == "MISS"
        assert self._get(superuser)["X-Cache"] == "HIT"
        assert self._get(other)["X-Cache"] == "MISS"
        assert self._get(other)["X-Cache"] == "HIT"

        bump_user_tile_version(str(superuser.das_tenant_id), str(superuser.id))

        # Busted user re-misses; the other user still hits.
        assert self._get(superuser)["X-Cache"] == "MISS"
        assert self._get(other)["X-Cache"] == "HIT"

    def test_bump_event_data_version_busts_all_users(self, superuser, create_user, located_event, patch_tile_tenant):
        other = create_user(is_superuser=True, username="other_super_data")
        assert self._get(superuser)["X-Cache"] == "MISS"
        assert self._get(superuser)["X-Cache"] == "HIT"
        assert self._get(other)["X-Cache"] == "MISS"
        assert self._get(other)["X-Cache"] == "HIT"

        bump_event_tile_data_version(str(superuser.das_tenant_id))

        assert self._get(superuser)["X-Cache"] == "MISS"
        assert self._get(other)["X-Cache"] == "MISS"


# --------------------------------------------------------------------------- #
# Cache version composition
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
class TestEventTileCacheVersion:
    def test_user_bump_changes_version(self):
        tenant_id, user_id = "t-1", "u-1"
        before = get_event_tile_cache_version(tenant_id, user_id)
        bump_user_tile_version(tenant_id, user_id)
        after = get_event_tile_cache_version(tenant_id, user_id)
        assert before != after

    def test_data_bump_changes_version(self):
        tenant_id, user_id = "t-2", "u-2"
        before = get_event_tile_cache_version(tenant_id, user_id)
        bump_event_tile_data_version(tenant_id)
        after = get_event_tile_cache_version(tenant_id, user_id)
        assert before != after

    def test_user_bump_isolated_per_user(self):
        bump_user_tile_version("t-3", "u-A")
        v_a = get_event_tile_cache_version("t-3", "u-A")
        v_b = get_event_tile_cache_version("t-3", "u-B")
        assert v_a != v_b


# --------------------------------------------------------------------------- #
# Binary MVT decode (requires mapbox-vector-tile)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventTileMvtDecode:
    def test_decoded_tile_contains_event_and_tile_fields(self, superuser, located_event, patch_tile_tenant):
        mvt = pytest.importorskip("mapbox_vector_tile")

        request = APIRequestFactory().get(_tile_url())
        request.user = superuser
        response = EventTileView.as_view()(request, Z, X, Y)
        assert response.status_code == 200

        decoded = mvt.decode(response.content)
        assert "events" in decoded
        features = decoded["events"]["features"]
        assert len(features) >= 1

        props = features[0]["properties"]
        assert props["event_type_value"] == "fire"
        assert props["event_category"] == "security"
        assert props["color"] == "red"
        assert props["image"] == "/static/sprite-src/fire-red.svg"
        assert str(located_event.serial_number) == str(props["serial_number"])


# --------------------------------------------------------------------------- #
# Event geometry layers (polygon fill + centroid)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventGeometryVectorLayerConfig:
    def test_polygon_fill_layer_configuration(self):
        layer = EventGeometryVectorLayer()
        assert layer.id == "event_geometries"
        assert layer.model is EventGeometry
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24

    def test_centroid_layer_configuration(self):
        layer = EventGeometryCentroidVectorLayer()
        assert layer.id == "event_centroids"
        assert layer.model is EventGeometry
        assert layer.min_zoom == 3
        assert layer.max_zoom == 24

    def test_tile_fields_include_styling_set_and_event_id(self):
        layer = EventGeometryVectorLayer()
        for field in (
            "id",
            "event_id",
            "serial_number",
            "event_type_value",
            "event_category",
            "color",
            "image",
        ):
            assert field in layer.tile_fields


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventGeometryGeographyCast:
    def test_polygon_fill_renders_in_web_mercator(self, polygon_only_event):
        obj = EventGeometryVectorLayer().get_queryset().filter(event_id=polygon_only_event.id).first()
        assert obj is not None
        assert obj.geom is not None
        assert obj.geom.srid == 3857
        assert obj.geom.geom_type == "Polygon"

    def test_centroid_is_point_within_source_polygon(self, polygon_only_event):
        obj = EventGeometryCentroidVectorLayer().get_queryset().filter(event_id=polygon_only_event.id).first()
        assert obj is not None
        assert obj.geom.geom_type == "Point"
        assert obj.geom.srid == 3857

        source = EventGeometry.objects.get(event_id=polygon_only_event.id).geometry
        centroid_wgs84 = obj.geom.transform(4326, clone=True)
        assert source.contains(centroid_wgs84)


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventGeometryAnnotations:
    def test_annotations_resolve_through_event_relation(self, polygon_only_event):
        obj = EventGeometryVectorLayer().get_queryset().filter(event_id=polygon_only_event.id).first()
        assert obj.event_id == polygon_only_event.id
        assert obj.event_type_value == "fire"
        assert obj.event_category == "security"
        # Urgent (300) + new -> red icon basename.
        assert obj.color == "red"
        assert obj.image == "/static/sprite-src/fire-red.svg"
        assert obj.event_time_iso.endswith("Z")


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventGeometryLayerParity:
    def test_point_only_event_absent_from_geometry_layers(self, located_event):
        # located_event has a point location but NO EventGeometry.
        assert EventGeometryVectorLayer().get_queryset().count() == 0
        assert EventGeometryCentroidVectorLayer().get_queryset().count() == 0

    def test_no_category_user_sees_no_geometries(self, user, polygon_only_event):
        request = _request_for(user)
        assert EventGeometryVectorLayer(request=request).get_queryset().count() == 0
        assert EventGeometryCentroidVectorLayer(request=request).get_queryset().count() == 0

    def test_bbox_retains_inside_drops_outside(self, das_tenant, superuser, security_event_type):
        inside = Event.objects.create(
            title="Inside polygon",
            event_type=security_event_type,
            location=None,
            das_tenant=das_tenant,
        )
        EventGeometry.objects.create(event=inside, geometry=_polygon_around(0.0, 0.0, half=0.5), das_tenant=das_tenant)
        outside = Event.objects.create(
            title="Outside polygon",
            event_type=security_event_type,
            location=None,
            das_tenant=das_tenant,
        )
        EventGeometry.objects.create(
            event=outside, geometry=_polygon_around(50.0, 50.0, half=0.5), das_tenant=das_tenant
        )
        request = _request_for(superuser, _tile_url() + "?bbox=-1,-1,1,1")
        event_ids = set(EventGeometryVectorLayer(request=request).get_queryset().values_list("event_id", flat=True))
        assert inside.id in event_ids
        assert outside.id not in event_ids

    def test_other_tenant_geometry_does_not_leak(self, das_tenant, polygon_only_event):
        import django_multitenant.utils

        from django.db.models.signals import post_save

        from activity.signals import ensure_perms_exist
        from factories import TenantFactory

        other_tenant = TenantFactory.create(id="11111111-1111-1111-1111-111111111111", domain="other.example.com")

        previous = django_multitenant.utils._context.tenant
        post_save.disconnect(ensure_perms_exist, sender=EventCategory)
        django_multitenant.utils._context.tenant = other_tenant
        try:
            other_cat = EventCategory.objects.create(value="iso_other", display="Other", das_tenant=other_tenant)
            other_et = EventType.objects.create(
                value="iso_other", display="Other", category=other_cat, das_tenant=other_tenant
            )
            other_event = Event.objects.create(
                title="Other tenant polygon event",
                event_type=other_et,
                location=None,
                das_tenant=other_tenant,
            )
            EventGeometry.objects.create(
                event=other_event,
                geometry=_polygon_around(EVENT_LON, EVENT_LAT),
                das_tenant=other_tenant,
            )
        finally:
            django_multitenant.utils._context.tenant = previous
            post_save.connect(ensure_perms_exist, sender=EventCategory)

        event_ids = set(EventGeometryVectorLayer().get_queryset().values_list("event_id", flat=True))
        assert polygon_only_event.id in event_ids
        assert other_event.id not in event_ids


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
class TestEventTileMvtDecodeGeometryLayers:
    def test_decoded_tile_contains_all_three_layers(
        self, superuser, located_event, polygon_only_event, patch_tile_tenant
    ):
        mvt = pytest.importorskip("mapbox_vector_tile")

        request = APIRequestFactory().get(_tile_url())
        request.user = superuser
        response = EventTileView.as_view()(request, Z, X, Y)
        assert response.status_code == 200

        decoded = mvt.decode(response.content)
        assert "events" in decoded
        assert "event_geometries" in decoded
        assert "event_centroids" in decoded

        geom_features = decoded["event_geometries"]["features"]
        assert len(geom_features) >= 1
        geom_props = geom_features[0]["properties"]
        assert str(geom_props["event_id"]) == str(polygon_only_event.id)
        assert geom_props["color"] == "red"
        assert geom_props["image"] == "/static/sprite-src/fire-red.svg"
        assert geom_features[0]["geometry"]["type"] in ("Polygon", "MultiPolygon")

        centroid_features = decoded["event_centroids"]["features"]
        assert len(centroid_features) >= 1
        centroid_props = centroid_features[0]["properties"]
        assert str(centroid_props["event_id"]) == str(polygon_only_event.id)
        assert centroid_props["image"] == "/static/sprite-src/fire-red.svg"
        assert centroid_features[0]["geometry"]["type"] == "Point"


@pytest.fixture(autouse=True)
def _clear_vector_tile_cache():
    """Keep the locmem vector-tile cache from leaking between tests."""
    caches["vector_tiles"].clear()
    yield
    caches["vector_tiles"].clear()
