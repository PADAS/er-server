"""
Vector layers for observation data.

Provides Mapbox Vector Tile layers for:
- Subject positions (Points) from SubjectStatus
- Track segments (LineStrings) from ObservationSegment

Both layers respect user permissions via:
- Subject group membership (users only see subjects in groups they have access to)
- delay_hours filtering (time-delayed access per permission level)
- MOU expiry date filtering
"""

import logging
from datetime import timedelta

from vectortiles import VectorLayer

from django.contrib.gis.db.models.functions import Transform
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    F,
    FloatField,
    Func,
    Value,
    When,
    Window,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce, Concat, Lower, RowNumber
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from observations.filters import ObservationSegmentVectorTileFilterSet
from observations.models import ObservationSegment, Subject
from observations.utils import get_minimum_allowed_age

logger = logging.getLogger(__name__)


class _ISOTimestamp(Func):
    """Format a timestamp as ISO 8601 (``2026-01-19T00:00:00.000Z``) in SQL.

    django-vectortiles generates MVT via ``ST_AsMVT`` entirely in PostgreSQL,
    so Python-level formatting (``as_vector_tile_feature``) is never invoked.
    We must format in SQL to give Mapbox GL lexicographically-sortable strings.
    """

    function = "to_char"
    template = "to_char(%(expressions)s AT TIME ZONE 'UTC'," ' \'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"\')'
    output_field = CharField()


class _CsvRgbToHex(Func):
    """Convert ``"R,G,B"`` (e.g. ``"255,0,128"``) to ``"#FF0080"`` in SQL.

    Falls back to the provided default when the input is NULL, empty, or
    cannot be parsed.  Uses ``split_part`` + ``lpad`` + ``to_hex`` which are
    available in PostgreSQL 9.5+.

    The JSON/text expression is evaluated in a scalar subquery so its bound
    parameters appear exactly once.  Repeating the same compiled SQL fragment
    multiple times in one expression can desync placeholders and params with
    some Django/psycopg paths (and broke tile/query execution).
    """

    output_field = CharField()

    def __init__(self, expression, default_hex="#4264FB", **extra):
        super().__init__(expression, **extra)
        self.default_hex = default_hex

    def as_sql(self, compiler, connection, **extra_context):
        connection.ops.check_expression_support(self)
        inner_sql, inner_params = compiler.compile(self.source_expressions[0])
        # Bind ``default_hex`` as a query parameter rather than splicing it into the SQL string.
        # Today it is always a hard-coded constant, but the constructor exposes it — defence in
        # depth in case a future caller passes user-controllable input.
        #
        # Only run the CAST path when the value matches a strict ``R,G,B`` pattern; otherwise
        # fall back to the default.  ``CAST(... AS INTEGER)`` aborts the whole query on
        # malformed input (``invalid input syntax for type integer``), which would 500 the
        # entire vector-tile request because of one bad row.
        sql = (
            f"(SELECT CASE "
            f"WHEN inner_v IS NULL OR inner_v = '' THEN %s "
            f"WHEN inner_v ~ '^\\s*[0-9]+\\s*,\\s*[0-9]+\\s*,\\s*[0-9]+\\s*$' THEN '#' "
            f"|| UPPER(LPAD(TO_HEX(CAST(BTRIM(SPLIT_PART(inner_v, ',', 1)) AS INTEGER)), 2, '0')) "
            f"|| UPPER(LPAD(TO_HEX(CAST(BTRIM(SPLIT_PART(inner_v, ',', 2)) AS INTEGER)), 2, '0')) "
            f"|| UPPER(LPAD(TO_HEX(CAST(BTRIM(SPLIT_PART(inner_v, ',', 3)) AS INTEGER)), 2, '0')) "
            f"ELSE %s "
            f"END FROM (SELECT ({inner_sql}) AS inner_v) _rgb_inner)"
        )
        return sql, [self.default_hex, self.default_hex, *inner_params]


class SubjectVectorLayer(VectorLayer):
    """
    Vector tile layer for subjects with their latest positions.

    Uses SubjectStatus to get current location for each subject, respecting
    user permissions via delay_hours calculation. Different users may see
    different positions based on their access_ends_N permissions.
    """

    model = Subject
    id = "subjects"
    min_zoom = 3
    max_zoom = 24

    def __init__(self, request=None):
        """
        Initialize layer with request context for permission-based filtering.

        Args:
            request: Django request object containing user and authentication
        """
        super().__init__()
        self.request = request
        self.delay_hours = 0  # Default to real-time
        self.mou_expiry_date = None

        # Calculate user-specific delay_hours from permissions (request set by view after permission_classes)
        if request and getattr(request, "user", None) is not None:
            min_age_days = get_minimum_allowed_age(request.user) or 0
            self.delay_hours = min_age_days * 24  # Convert days to hours

            # Get MOU expiry date if present
            if hasattr(request.user, "additional") and request.user.additional:
                self.mou_expiry_date = request.user.additional.get("expiry", None)

    @property
    def tile_fields(self):
        """Fields to include in vector tiles.

        ``icon_url`` is the resolved icon path built from subtype, radio_state
        colour, and sex so the client can load it directly via styleimagemissing.
        """
        return (
            "id",
            "name",
            "subject_type_value",
            "subject_subtype_value",
            "icon_url",
            "color",
            "radio_state",
            "recorded_at",
            "is_active",
        )

    def _get_geometry_field(self):
        """
        Transform status_location from WGS84 (4326) to Web Mercator (3857).

        The status_location field comes from annotate_with_subjectstatus()
        and contains the subject's position at the appropriate delay_hours.
        """
        return Transform(F("status_location"), 3857)

    def get_queryset(self):
        """
        Build the base queryset for vector tiles.

        Returns subjects with their position from SubjectStatus using
        user-specific delay_hours, including icon URLs, colors, and device status.

        Subject group permission filtering is applied for non-superusers via
        the same ``by_user_subjects`` queryset method used by every other
        subject endpoint, ensuring a single source of truth for access control.
        """
        qs = self.model.objects.all()

        # Apply subject group permission filtering for non-superusers
        if self.request and getattr(self.request, "user", None) is not None and not self.request.user.is_superuser:
            qs = qs.by_user_subjects(self.request.user)

        # Annotate with status at the user's permitted delay_hours
        qs = qs.annotate_with_subjectstatus(
            delay_hours=self.delay_hours,
            mou_expiry_date=self.mou_expiry_date,
        ).select_related("subject_subtype")

        # Filter out subjects without location at this delay window
        qs = qs.filter(status_location__isnull=False)

        # Extract color from subject.additional["rgb"] or use default
        color_expr = Case(
            When(
                additional__has_key="rgb",
                then=KeyTextTransform("rgb", F("additional")),
            ),
            default=Value("255,255,0"),  # Default yellow
            output_field=CharField(),
        )

        # Map radio_state → icon colour, matching STATUS_COLORS in models.py
        icon_color_expr = Case(
            When(status_radio_state="online-gps", then=Value("green")),
            When(status_radio_state="online", then=Value("blue")),
            When(status_radio_state="offline", then=Value("gray")),
            When(status_radio_state="alarm", then=Value("red")),
            default=Value("black"),
            output_field=CharField(),
        )

        # Build image path: /static/sprite-src/{subtype}-{color}-{sex}.svg
        # Mirrors Subject._image_keys() primary key; styleimagemissing on
        # the client handles any fallback if this specific file is missing.
        sex_expr = Case(
            When(
                additional__has_key="sex",
                then=KeyTextTransform("sex", F("additional")),
            ),
            default=Value("male"),
            output_field=CharField(),
        )

        image_url_expr = Concat(
            Value("/static/sprite-src/"),
            Lower(Coalesce(F("subject_subtype__value"), Value("pin"))),
            Value("-"),
            icon_color_expr,
            Value("-"),
            Lower(sex_expr),
            Value(".svg"),
            output_field=CharField(),
        )

        # Annotate with required fields (subject_type_value avoids shadowing Subject.subject_type FK)
        # Use icon_url (not image_url) to avoid shadowing Subject's read-only image_url property.
        return qs.annotate(
            geom=self._get_geometry_field(),
            subject_type_value=F("subject_subtype__subject_type__value"),
            subject_subtype_value=Coalesce(F("subject_subtype__value"), Value("")),
            icon_url=image_url_expr,
            color=color_expr,
            radio_state=F("status_radio_state"),
            recorded_at=F("status_recorded_at"),
        )


class ObservationSegmentVectorLayer(VectorLayer):
    """
    Vector layer for pre-computed observation segments.

    Returns LineString features representing segments between consecutive observations.
    Each segment includes computed metrics (speed, time gap, distance) and
    presentation properties for client-side rendering.

    Respects user permissions by filtering segments to match the user's permitted
    time window (delay_hours). This ensures track segments align with subject positions
    shown based on access_ends_N permissions.
    """

    model = ObservationSegment
    id = "observation_segments"
    geom_field = "geometry"
    min_zoom = 3
    max_zoom = 24
    filterset_class = ObservationSegmentVectorTileFilterSet

    def __init__(self, request=None):
        """
        Initialize layer with request context for permission-based filtering.

        Args:
            request: Django request object containing user and authentication
        """
        super().__init__()
        self.request = request
        self.delay_hours = 0  # Default to real-time
        self.mou_expiry_date = None

        # Calculate user-specific delay_hours from permissions (request set by view after permission_classes)
        if request and getattr(request, "user", None) is not None:
            min_age_days = get_minimum_allowed_age(request.user) or 0
            self.delay_hours = min_age_days * 24  # Convert days to hours

            # Get MOU expiry date if present
            if hasattr(request.user, "additional") and request.user.additional:
                self.mou_expiry_date = request.user.additional.get("expiry", None)

    # ------------------------------------------------------------------ #
    # Presentation / appearance
    # ------------------------------------------------------------------ #
    @property
    def presentation_keys(self):
        return ["stroke", "stroke_width", "stroke_opacity"]

    @property
    def tile_fields(self):
        return (
            "id",
            "subject_id",
            "subject_name",
            "start_time",
            "end_time",
            "speed_kmh",
            "time_gap_ms",
            "distance_meters",
            "bearing_deg",
            "exclusion_flags",
            "is_latest",
            "stroke",
            "stroke_width",
            "stroke_opacity",
        )

    # ------------------------------------------------------------------ #
    # Query construction
    # ------------------------------------------------------------------ #
    def get_queryset(self):
        """
        Build queryset for segments with annotations.

        Subject group permission filtering is applied for non-superusers,
        restricting segments to only those belonging to subjects the user
        has access to via their permission sets and subject group membership.

        Applies ObservationSegmentVectorTileFilterSet (range, show_excluded)
        from request GET params. Also applies permission-based time window
        (delay_hours) and MOU expiry.
        """
        qs = self.model.objects.select_related("subject", "subject__subject_subtype")

        # Apply subject group permission filtering for non-superusers
        if self.request and getattr(self.request, "user", None) is not None and not self.request.user.is_superuser:
            allowed_subjects = Subject.objects.by_user_subjects(self.request.user)
            qs = qs.filter(subject__in=allowed_subjects)

        # Apply permission-based time filtering
        # Filter segments to only show data up to the user's permitted time window
        if self.delay_hours > 0:
            # Calculate cutoff: now minus delay_hours = furthest "present" the user can see
            cutoff_time = timezone.now() - timedelta(hours=self.delay_hours)
            # Only show segments that ended before the cutoff
            qs = qs.filter(end_recorded_at__lte=cutoff_time)

        # Apply MOU expiry date filtering if present
        if self.mou_expiry_date:
            expiry_dt = (
                parse_datetime(self.mou_expiry_date) if isinstance(self.mou_expiry_date, str) else self.mou_expiry_date
            )
            if expiry_dt:
                qs = qs.filter(end_recorded_at__lte=expiry_dt)

        # Apply filterset (range, show_excluded) from request params or defaults
        if self.request is not None:
            filterset = self.filterset_class(data=self.request.GET, queryset=qs)
            qs = filterset.qs
        # When no request (e.g. some tests), use defaults via filterset with empty data
        else:
            filterset = self.filterset_class(data={}, queryset=qs)
            qs = filterset.qs

        return qs.order_by("start_recorded_at")

    def _get_vector_tile_annotations(self):
        """
        Return annotations for vector tile output.

        ``start_time`` / ``end_time`` are ISO 8601-formatted aliases for the
        segment's ``start_recorded_at`` / ``end_recorded_at``, computed **in SQL**
        so that ``ST_AsMVT`` emits lexicographically-sortable strings the client
        can use in Mapbox GL filter expressions.

        ``stroke`` / ``stroke_width`` / ``stroke_opacity`` are presentation
        properties derived from the subject's ``additional->>'rgb'`` field.
        MVT property names use underscores (SQL column alias limitation); the
        client style layer should reference ``stroke_width`` / ``stroke_opacity``.
        """
        return {
            "subject_name": Coalesce(F("subject__name"), Value("", output_field=CharField())),
            "start_time": _ISOTimestamp(F("start_recorded_at")),
            "end_time": _ISOTimestamp(F("end_recorded_at")),
            "stroke": _CsvRgbToHex(
                KeyTextTransform("rgb", F("subject__additional")),
                default_hex="#FFFF00",
            ),
            "stroke_width": Value(2.0, output_field=FloatField()),
            "stroke_opacity": Value(0.8, output_field=FloatField()),
        }

    def get_vector_tile_queryset(self, z=None, x=None, y=None):
        """
        Build queryset for vector tile extraction with tile-specific optimizations.
        """
        qs = self.get_queryset()
        annotations = self._get_vector_tile_annotations()

        # Flag the latest segment per subject within the filtered queryset
        rn = Window(
            expression=RowNumber(),
            partition_by=F("subject_id"),
            order_by=[F("end_recorded_at").desc()],
        )
        qs = qs.annotate(_rn=rn)
        qs = qs.annotate(
            is_latest=Case(When(_rn=1, then=Value(True)), default=Value(False), output_field=BooleanField())
        )

        return qs.annotate(**annotations)

    # ------------------------------------------------------------------ #
    # Styling / presentation
    # ------------------------------------------------------------------ #
    def get_presentation_properties(self, obj):
        """Return stroke presentation properties for a segment feature.

        Uses the subject's ``color`` property (which converts ``additional["rgb"]``
        from CSV ``"R,G,B"`` to hex ``"#RRGGBB"``).  Property names use underscores
        to match the SQL annotation path used by the PostGIS MVT backend.
        """
        subject = obj.subject
        # Match the SQL/MVT default in ``_get_vector_tile_annotations`` so the Python
        # feature path renders the same color as ST_AsMVT when ``additional['rgb']`` is
        # missing or malformed (``Subject.color`` returns ``None`` for bad CSV).
        stroke = getattr(subject, "color", None) or "#FFFF00"
        return {
            "stroke": stroke,
            "stroke_width": 2.0,
            "stroke_opacity": 0.8,
        }

    def as_vector_tile_feature(self, obj):
        """
        Return feature dict for vector tile rendering.

        With the default django-vectortiles PostGIS backend, MVT is generated
        entirely in SQL via ``ST_AsMVT``, so that code path does not call this
        method; timestamp formatting is done in annotations (see ``_ISOTimestamp``).
        This method is for non-MVT callers (e.g. tests or other backends that
        iterate Python objects). Callers must ensure the same annotations from
        ``_get_vector_tile_annotations`` (including ``start_time`` and ``end_time``)
        are present on ``obj`` before calling, or AttributeError may occur.
        """

        def _iso(val):
            """Format a datetime (or pre-formatted string) as ISO 8601."""
            if val is None:
                return None
            if isinstance(val, str):
                return val
            return val.isoformat(sep="T", timespec="milliseconds")

        start_time = obj.start_recorded_at
        end_time = obj.end_recorded_at
        props = {
            "id": str(obj.id),
            "subject_id": str(obj.subject_id),
            "subject_name": getattr(obj, "subject_name", ""),
            "start_time": _iso(start_time),
            "end_time": _iso(end_time),
            "speed_kmh": round(obj.speed_kmh, 2) if obj.speed_kmh else None,
            "time_gap_ms": round(obj.time_gap_ms, 0) if obj.time_gap_ms else None,
            "distance_meters": round(obj.distance_meters, 2) if obj.distance_meters else None,
            "bearing_deg": round(obj.bearing_deg, 2) if obj.bearing_deg is not None else None,
            "exclusion_flags": obj.exclusion_flags.mask if hasattr(obj.exclusion_flags, "mask") else 0,
            "is_latest": bool(getattr(obj, "is_latest", False)),
        }

        # Add presentation properties
        props.update(self.get_presentation_properties(obj))

        return {
            "id": str(obj.id),
            "geometry": obj.geometry,
            "properties": props,
        }
