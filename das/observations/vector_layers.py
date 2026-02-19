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

from vectortiles import VectorLayer

from django.contrib.gis.db.models.functions import Transform
from django.db.models import BooleanField, Case, CharField, F, Func, Value, When, Window
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce, Concat, Lower, RowNumber


class _ISOTimestamp(Func):
    """Format a timestamp as ISO 8601 (``2026-01-19T00:00:00.000Z``) in SQL.

    django-vectortiles generates MVT via ``ST_AsMVT`` entirely in PostgreSQL,
    so Python-level formatting (``as_vector_tile_feature``) is never invoked.
    We must format in SQL to give Mapbox GL lexicographically-sortable strings.
    """

    function = "to_char"
    template = (
        "to_char(%(expressions)s AT TIME ZONE 'UTC',"
        " 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"')"
    )
    output_field = CharField()

from observations.filters import ObservationSegmentVectorTileFilterSet
from observations.models import ObservationSegment, Subject

logger = logging.getLogger(__name__)


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

        # Calculate user-specific delay_hours from permissions
        if request and hasattr(request, "user") and request.user.is_authenticated:
            from observations.utils import get_minimum_allowed_age

            min_age_days = get_minimum_allowed_age(request.user) or 0
            self.delay_hours = min_age_days * 24  # Convert days to hours

            # Get MOU expiry date if present
            if hasattr(request.user, "additional") and request.user.additional:
                self.mou_expiry_date = request.user.additional.get("expiry", None)

    @property
    def tile_fields(self):
        """Fields to include in vector tiles.

        ``image_url`` is the resolved icon path built from subtype, radio_state
        colour, and sex so the client can load it directly via styleimagemissing.
        """
        return (
            "id",
            "name",
            "subject_type",
            "subject_subtype_value",
            "image_url",
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
        if self.request and hasattr(self.request, "user") and self.request.user.is_authenticated:
            if not self.request.user.is_superuser:
                qs = qs.by_user_subjects(self.request.user)

        # Annotate with status at the user's permitted delay_hours
        qs = qs.annotate_with_subjectstatus(
            delay_hours=self.delay_hours,
            mou_expiry_date=self.mou_expiry_date,
        ).select_related("subject_subtype", "subject_subtype__subject_type")

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

        # Annotate with required fields
        return qs.annotate(
            geom=self._get_geometry_field(),
            subject_type=F("subject_subtype__subject_type__value"),
            subject_subtype_value=Coalesce(F("subject_subtype__value"), Value("")),
            image_url=image_url_expr,
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

        # Calculate user-specific delay_hours from permissions
        if request and hasattr(request, "user") and request.user.is_authenticated:
            from observations.utils import get_minimum_allowed_age

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
        return ["stroke", "stroke-width", "stroke-opacity"]

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

        By default, excludes segments with non-zero exclusion flags.
        Filters segments to respect user's permitted time window (delay_hours).
        """
        qs = self.model.objects.select_related("subject", "subject__subject_subtype")

        # Apply subject group permission filtering for non-superusers
        if self.request and hasattr(self.request, "user") and self.request.user.is_authenticated:
            if not self.request.user.is_superuser:
                allowed_subjects = Subject.objects.by_user_subjects(self.request.user)
                qs = qs.filter(subject__in=allowed_subjects)

        # Apply default exclusion unless 'show_excluded=true'
        if hasattr(self, "request") and self.request:
            show_excluded = (self.request.GET.get("show_excluded", "false") or "false").lower() == "true"
            if not show_excluded:
                qs = qs.filter(exclusion_flags=0)

        # Apply permission-based time filtering
        # Filter segments to only show data up to the user's permitted time window
        if self.delay_hours > 0:
            from datetime import timedelta

            from django.utils import timezone

            # Calculate cutoff: now minus delay_hours = furthest "present" the user can see
            cutoff_time = timezone.now() - timedelta(hours=self.delay_hours)
            # Only show segments that ended before the cutoff
            qs = qs.filter(end_recorded_at__lte=cutoff_time)

        # Apply MOU expiry date filtering if present
        if self.mou_expiry_date:
            from django.utils.dateparse import parse_datetime

            expiry_dt = (
                parse_datetime(self.mou_expiry_date) if isinstance(self.mou_expiry_date, str) else self.mou_expiry_date
            )
            if expiry_dt:
                qs = qs.filter(end_recorded_at__lte=expiry_dt)

        return qs.order_by("start_recorded_at")

    def _get_vector_tile_annotations(self):
        """
        Return annotations for vector tile output.

        ``start_time`` / ``end_time`` are ISO 8601-formatted aliases for the
        segment's ``start_recorded_at`` / ``end_recorded_at``, computed **in SQL**
        so that ``ST_AsMVT`` emits lexicographically-sortable strings the client
        can use in Mapbox GL filter expressions.
        """
        return {
            "subject_name": Coalesce(F("subject__name"), Value("", output_field=CharField())),
            "start_time": _ISOTimestamp(F("start_recorded_at")),
            "end_time": _ISOTimestamp(F("end_recorded_at")),
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
        """
        Return presentation properties for a segment feature.
        Uses subject's color/style settings.
        """
        subject = obj.subject
        additional = getattr(subject, "additional", {}) or {}

        # Default track styling
        stroke = additional.get("rgb", "#4264fb")  # Default blue
        stroke_width = 2.0
        stroke_opacity = 0.8

        # You can add logic here to vary stroke based on speed, time_gap, etc.
        # For example: thicker lines for faster speeds, dashed for long time gaps

        return {
            "stroke": stroke,
            "stroke-width": stroke_width,
            "stroke-opacity": stroke_opacity,
        }

    def as_vector_tile_feature(self, obj):
        """
        Return feature dict for vector tile rendering.

        With the default django-vectortiles PostGIS backend, MVT is generated
        entirely in SQL via ``ST_AsMVT``, so that code path does not call this
        method; timestamp formatting is done in annotations (see ``_ISOTimestamp``).
        This method is for non-MVT callers (e.g. tests or other backends that
        iterate Python objects). Such callers must ensure the same annotations
        from ``_get_vector_tile_annotations`` (including ``start_time`` and
        ``end_time``) are present on ``obj`` before calling.
        """

        # Ensure ISO 8601 with 'T' separator for lexicographic sorting
        def _iso(dt):
            return dt.isoformat(sep="T", timespec="milliseconds") if dt else None

        props = {
            "id": str(obj.id),
            "subject_id": str(obj.subject_id),
            "subject_name": getattr(obj, "subject_name", ""),
            "start_time": _iso(obj.start_time),
            "end_time": _iso(obj.end_time),
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
