"""Vector layers for activity (events) data.

Provides a Mapbox Vector Tile layer for Events (Points from ``Event.location``).

The layer respects the full ``/activity/events`` filter + permission surface by
reusing the same DRF filter backends (``EventPermissionsFilter``,
``EventListFilter``, ``EventSubjectsFilter``) verbatim, so tile scoping is
identical to the events list API.

django-vectortiles renders MVT entirely in PostGIS via ``ST_AsMVT``, so every
tile field must be expressed as a SQL annotation (``Case``/``When``/``Func``);
Python-level feature formatting is never invoked on the MVT path.
"""

from __future__ import annotations

import logging

from vectortiles import VectorLayer

from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.db.models.functions import PointOnSurface, Transform
from django.db.models import (
    BigIntegerField,
    BooleanField,
    Case,
    CharField,
    F,
    Func,
    QuerySet,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce, Concat, NullIf
from rest_framework.request import Request

from activity.filters import (
    EventListFilter,
    EventPermissionsFilter,
    EventSubjectsFilter,
)
from activity.models import Event, EventGeometry

logger = logging.getLogger(__name__)


def _apply_event_filter_backends(request: Request | None, qs: QuerySet) -> QuerySet:
    """Apply the three /activity/events DRF filter backends in EventsView order.

    No-op when request/user is absent. Shared by the point and geometry event
    tile layers so their scoping (filters + category/geo permissions + related-
    subject visibility) stays in lockstep.
    """
    if request is not None and getattr(request, "user", None) is not None:
        qs = EventPermissionsFilter().filter_queryset(request, qs, view=None)
        qs = EventListFilter().filter_queryset(request, qs, view=None)
        qs = EventSubjectsFilter().filter_queryset(request, qs, view=None)
    return qs


class _ISOTimestamp(Func):
    """Format a timestamp as ISO 8601 (``2026-01-19T00:00:00.000Z``) in SQL.

    Cloned from ``observations.vector_layers._ISOTimestamp``: django-vectortiles
    generates MVT via ``ST_AsMVT`` entirely in PostgreSQL, so Python-level
    formatting is never invoked. Formatting in SQL gives Mapbox GL
    lexicographically-sortable strings for client-side filter expressions.
    """

    function = "to_char"
    template = "to_char(%(expressions)s AT TIME ZONE 'UTC'," ' \'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"\')'
    output_field = CharField()


class _EpochMillis(Func):
    """Format a timestamp as an integer millisecond epoch in SQL.

    django-vectortiles generates MVT via ``ST_AsMVT`` entirely in PostgreSQL, so
    Python-level formatting is never invoked. The integer epoch-millisecond value
    allows client-side time arithmetic (e.g. the map's time-slider fade gradient)
    which is not possible with the lexicographic ISO-8601 string form.

    ``BigIntegerField`` is required because current epoch-ms values (~1.75e12)
    overflow a 32-bit integer.
    """

    template = "(floor(extract(epoch from %(expressions)s) * 1000))::bigint"
    output_field = BigIntegerField()


class _DisplayTimestamp(Func):
    """Format a timestamp as a human-readable, fixed-UTC display string in SQL.

    Produces strings like ``Jun 24, 14:30 UTC`` for use as the date line of the
    on-map event label. Mapbox GL's styling engine cannot format dates client-side,
    so the server must emit a ready-to-display string in the MVT feature properties.

    Locale note: ``to_char``'s month-name output (the ``Mon`` pattern) depends on
    the database ``lc_time`` locale. In this deployment that yields English
    abbreviations (e.g. "Jun", "Dec"); this is the one locale-sensitive part of
    the output. All other formatting is locale-independent.
    """

    function = "to_char"
    template = "to_char(%(expressions)s AT TIME ZONE 'UTC', 'Mon DD, HH24:MI \"UTC\"')"
    output_field = CharField()


class _EventStylingMixin:
    """SQL builders for event icon color / image, single-sourced across layers.

    The color/image expressions mirror ``Event.image_basename`` and must be kept
    in sync with it. They are shared by the point layer (``EventVectorLayer``,
    fields on ``Event`` directly, ``prefix=""``) and the geometry layers
    (``_EventGeometryLayerBase``, fields reached through the ``event`` relation,
    ``prefix="event__"``) so icon/color rendering can never drift between them.
    """

    def _priority_color_case(self, prefix: str) -> Case:
        """Priority -> icon color, mirroring ``Event.image_basename`` / ``CONVERSION``.

        Kept in sync with activity.models.Event.image_basename.
        """
        return Case(
            When(**{f"{prefix}priority": Event.PRI_NONE}, then=Value("gray")),
            When(**{f"{prefix}priority": Event.PRI_REFERENCE}, then=Value("med_green")),
            When(**{f"{prefix}priority": Event.PRI_IMPORTANT}, then=Value("amber")),
            When(**{f"{prefix}priority": Event.PRI_URGENT}, then=Value("red")),
            default=Value("black"),
            output_field=CharField(),
        )

    def _color_expr(self, prefix: str) -> Case:
        """Resolve icon color from priority + state, mirroring ``image_basename``.

        Resolved events render ``lt_gray`` regardless of priority.
        """
        return Case(
            When(**{f"{prefix}state": Event.SC_RESOLVED}, then=Value("lt_gray")),
            default=self._priority_color_case(prefix),
            output_field=CharField(),
        )

    def _icon_basename_expr(self, prefix: str) -> Concat:
        """Build the icon basename ``{event_type}-{color}`` in SQL.

        Uses ``event_type.icon`` when set, else ``event_type.value`` (matching
        ``EventType.icon_id``'s primary preference). ``other`` stands in when no
        event type is present, matching ``Event.image_basename``.
        """
        event_type_token = Coalesce(
            NullIf(F(f"{prefix}event_type__icon"), Value("")),
            F(f"{prefix}event_type__value"),
            Value("other"),
            output_field=CharField(),
        )
        return Concat(event_type_token, Value("-"), self._color_expr(prefix), output_field=CharField())

    def _image_expr(self, prefix: str) -> Concat:
        """Build the resolved icon path ``/static/sprite-src/{basename}.svg`` in SQL.

        Mirrors ``StaticImageFinder``'s ``sprite-src`` path. The client's
        ``styleimagemissing`` handles any missing-file fallback (the SQL path
        cannot walk the multi-key fallback chain the Python finder uses).
        """
        return Concat(
            Value("/static/sprite-src/"),
            self._icon_basename_expr(prefix),
            Value(".svg"),
            output_field=CharField(),
        )


class EventVectorLayer(_EventStylingMixin, VectorLayer):
    """Vector tile layer for Events as Point features.

    Geometry is ``Event.location`` transformed to Web Mercator (SRID 3857) on the
    fly. Events are points that churn constantly under a short (3-5 min) tile TTL,
    so a precomputed web-mercator column (as ``SpatialFeature`` has) is a
    deliberate non-goal here; revisit if profiling shows need.

    Written as a request-aware, permission-filtered layer (mirrors
    ``SubjectVectorLayer``) and registered via ``layer_classes`` (list form) so the
    endpoint can later become a multi-class layer (events + subjects) without a
    rewrite. ``EventGeometry`` polygons/lines can be added as a follow-up.
    """

    model = Event
    id = "events"
    min_zoom = 3
    max_zoom = 24

    def __init__(self, request: Request | None = None) -> None:
        """Store request context; permission filtering happens in ``get_queryset``.

        The view sets ``request`` after ``permission_classes`` run, matching the
        subject/segment layers.
        """
        super().__init__()
        self.request = request

    @property
    def tile_fields(self) -> tuple[str, ...]:
        """Properties emitted on each event feature for client-side styling.

        NOTE: This starting set mirrors ``make_feature`` / ``EventGeoJsonSerializer``
        and is pending front-end sign-off (ticket requirement). Adjust once FE
        confirms the exact fields they need to style events without extra
        round-trips.
        """
        return (
            "id",
            "serial_number",
            "event_type_value",
            "event_category",
            "priority",
            "state",
            "title",
            "event_time_iso",
            "event_time_ms",
            "event_time_display",
            "updated_at_iso",
            "updated_at_ms",
            "is_collection",
            "image",
            "color",
        )

    def _get_geometry_field(self) -> Transform:
        """Transform ``Event.location`` from WGS84 (4326) to Web Mercator (3857)."""
        return Transform(F("location"), 3857)

    def get_queryset(self) -> QuerySet:
        """Build the base queryset for event vector tiles.

        Tenant isolation is automatic via ``Event.objects`` (``TenantManagerMixin``).
        The three events filter backends are applied in the same order as
        ``EventsView`` so tile scoping (filters + category/geo permissions +
        related-subject visibility) is identical to ``/activity/events``. The
        backends short-circuit appropriately for superusers (e.g. ``by_location``
        returns all; ``EventSubjectsFilter`` is governed by ``by_user_subjects``).

        Annotated aliases (``event_type_value`` / ``event_time_iso`` /
        ``event_time_ms`` / ``event_time_display`` / ``updated_at_iso`` /
        ``updated_at_ms`` / ``is_collection``) carry the value / ISO-string /
        integer epoch-ms / preformatted UTC display string / boolean so
        ``ST_AsMVT`` renders client-friendly scalars rather than FK ids or DB
        datetimes. The ``_ms`` aliases carry the integer millisecond-epoch value
        for client-side time arithmetic (e.g. the map's time-slider fade
        gradient). ``event_time_display`` carries a human-readable fixed-UTC
        string (e.g. ``Jun 24, 14:30 UTC``) for the map label's date line, since
        Mapbox GL cannot format dates client-side. Alias names differ from the
        model field names because Django forbids an annotation that collides with
        a concrete field.
        """
        qs = _apply_event_filter_backends(self.request, self.model.objects.all().filter(location__isnull=False))

        return qs.select_related("event_type", "event_type__category").annotate(
            geom=self._get_geometry_field(),
            event_type_value=Coalesce(F("event_type__value"), Value(""), output_field=CharField()),
            event_category=Coalesce(F("event_type__category__value"), Value(""), output_field=CharField()),
            event_time_iso=_ISOTimestamp(F("event_time")),
            event_time_ms=_EpochMillis(F("event_time")),
            event_time_display=_DisplayTimestamp(F("event_time")),
            updated_at_iso=_ISOTimestamp(F("updated_at")),
            updated_at_ms=_EpochMillis(F("updated_at")),
            is_collection=Coalesce(F("event_type__is_collection"), Value(False), output_field=BooleanField()),
            color=self._color_expr(""),
            image=self._image_expr(""),
        )


class _EventGeometryLayerBase(_EventStylingMixin, VectorLayer):
    """Base for event geometry tile layers (polygon fill + icon-anchor centroid).

    Sources from ``EventGeometry`` and reaches the styling/scalar fields through
    the ``event`` relation, so polygon-only events (null ``Event.location`` with a
    drawn ``EventGeometry``) render in tiles. Scoping reuses the same
    ``/activity/events`` filter backends as ``EventVectorLayer`` (via
    ``_apply_event_filter_backends``) so the two stay in lockstep.

    ``EventGeometry.geometry`` is a geography column (``GeometryField(srid=4326,
    geography=True)``); ``ST_Transform`` is geometry-only, so concrete subclasses
    cast to geometry before transforming.
    """

    model = EventGeometry
    min_zoom = 3
    max_zoom = 24

    def __init__(self, request: Request | None = None) -> None:
        """Store request context; permission filtering happens in ``get_queryset``."""
        super().__init__()
        self.request = request

    @property
    def tile_fields(self) -> tuple[str, ...]:
        """Properties emitted on each geometry feature.

        Mirrors ``EventVectorLayer.tile_fields`` so fill/fade/icon style
        identically, plus ``event_id`` to link a geometry feature back to its
        event. Pending front-end sign-off, like the point layer's set.
        """
        return (
            "id",
            "event_id",
            "serial_number",
            "event_type_value",
            "event_category",
            "priority",
            "state",
            "title",
            "event_time_iso",
            "event_time_ms",
            "event_time_display",
            "updated_at_iso",
            "updated_at_ms",
            "is_collection",
            "image",
            "color",
        )

    def _get_geometry_field(self) -> Transform:
        raise NotImplementedError

    def get_queryset(self) -> QuerySet:
        """Build the base queryset for event geometry vector tiles.

        Tenant isolation is automatic via ``EventGeometry.objects`` and the
        ``event_id__in`` subquery on the (also tenant-scoped) filtered events.
        The event filter backends run against ``Event.objects.all()`` with NO
        ``location`` filter so polygon-only events are retained. Scalar / styling
        fields are annotated through the ``event`` relation so ``ST_AsMVT``
        renders client-friendly values rather than FK ids.
        """
        events = _apply_event_filter_backends(self.request, Event.objects.all())
        qs = self.model.objects.filter(event_id__in=events.values("id"))
        return qs.select_related("event", "event__event_type", "event__event_type__category").annotate(
            geom=self._get_geometry_field(),
            serial_number=F("event__serial_number"),
            event_type_value=Coalesce(F("event__event_type__value"), Value(""), output_field=CharField()),
            event_category=Coalesce(F("event__event_type__category__value"), Value(""), output_field=CharField()),
            priority=F("event__priority"),
            state=F("event__state"),
            title=F("event__title"),
            event_time_iso=_ISOTimestamp(F("event__event_time")),
            event_time_ms=_EpochMillis(F("event__event_time")),
            event_time_display=_DisplayTimestamp(F("event__event_time")),
            updated_at_iso=_ISOTimestamp(F("event__updated_at")),
            updated_at_ms=_EpochMillis(F("event__updated_at")),
            is_collection=Coalesce(F("event__event_type__is_collection"), Value(False), output_field=BooleanField()),
            color=self._color_expr("event__"),
            image=self._image_expr("event__"),
        )


class EventGeometryVectorLayer(_EventGeometryLayerBase):
    """Polygon-fill tile layer for ``EventGeometry`` shapes (layer id ``event_geometries``)."""

    id = "event_geometries"

    def _get_geometry_field(self) -> Transform:
        return Transform(Cast(F("geometry"), GeometryField(srid=4326)), 3857)


class EventGeometryCentroidVectorLayer(_EventGeometryLayerBase):
    """Server-computed icon-anchor point per geometry (layer id ``event_centroids``).

    Emits ``ST_PointOnSurface`` (guaranteed inside concave / donut shapes) so the
    front end places exactly one event icon at a stable in-polygon position at
    every zoom, even though MVT clips polygons to tile boundaries.
    """

    id = "event_centroids"

    def _get_geometry_field(self) -> Transform:
        return Transform(PointOnSurface(Cast(F("geometry"), GeometryField(srid=4326))), 3857)
