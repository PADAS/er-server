import logging
import re

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework_condition import etag

from django.db.models import F, QuerySet, Window
from django.db.models.functions import FirstValue
from django.db.utils import IntegrityError
from django.forms import ValidationError
from rest_framework import status
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.response import Response

from observations.filters import create_gp_filter_class
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import SourceGroup, Subject, SubjectGroup, SubjectSource
from observations.permissions import SubjectModelPermissions
from observations.serializers import (
    SubjectGeoJsonSerializer,
    SubjectIdSerializer,
    SubjectSerializer,
    create_sg_serializer,
)
from observations.serializers.all_groups import AllGroupsSerializer
from observations.utils import (
    VIEW_SOURCE_PERMS,
    VIEW_SUBJECT_PERMS,
    check_to_include_inactive_subjects,
    check_valid_date_string,
    dateparse,
    get_minimum_allowed_age,
)
from observations.views.schemas import SubjectGroupsViewSchema
from observations.views.utils import (
    SubjectGroupGetQuerySet,
    all_group_subjects_etag,
    build_groups_hierarchy_with_all_subjects,
    default_since,
    get_track_days,
    subject_group_etag,
)
from schemas.view_mixins import DynamicSchemaDataMixin
from utils.drf import (
    BadRequestAPIException,
    ForbiddenAPIException,
    OptionalResultsSetPagination,
    StandardObjectPermissions,
    StandardResultsSetGeoJsonPagination,
    return_409_response,
)
from utils.json import ExtendedGEOJSONRenderer, parse_bool
from utils.schema_utils import is_uuid
from utils.tenant.thread import get_tenant_settings

logger = logging.getLogger(__name__)


SUBJECTS_LIST_PARAMS = [
    # from InactiveSubjectsViewSchema
    OpenApiParameter(
        name="include_inactive",
        location=OpenApiParameter.QUERY,
        description="Include inactive subjects in list.",
        type=OpenApiTypes.BOOL,
        required=False,
    ),
    OpenApiParameter(
        name="tracks_since",
        location=OpenApiParameter.QUERY,
        description="Include tracks since this timestamp (ISO8601).",
        type=OpenApiTypes.DATETIME,
        required=False,
    ),
    OpenApiParameter(
        name="tracks_until",
        location=OpenApiParameter.QUERY,
        description="Include tracks up through this timestamp (ISO8601).",
        type=OpenApiTypes.DATETIME,
        required=False,
    ),
    OpenApiParameter(
        name="bbox",
        location=OpenApiParameter.QUERY,
        description=(
            "Include subjects having track data within this bounding box defined "
            "as west,south,east,north (comma-separated). "
            "Example: -77.2,-12.3,-76.7,-11.9"
        ),
        type=OpenApiTypes.STR,
        required=False,
    ),
    OpenApiParameter(
        name="subject_group",
        location=OpenApiParameter.QUERY,
        description=(
            "Single UUID or comma-separated UUIDs. "
            "Returns subjects that belong to ANY listed group. "
            "If the subject group ID is one UUID only, it will return subjects of nested groups of the group. "
            "Examples: 123e4567-e89b-12d3-a456-426614174000 or "
            "123e4567-e89b-12d3-a456-426614174000,987e6543-e21b-54d3-a654-426614174999"
        ),
        type=OpenApiTypes.STR,  # no `schema=` here
        style="form",
        explode=False,
    ),
    OpenApiParameter(
        name="name",
        location=OpenApiParameter.QUERY,
        description="Find subjects with the given name.",
        type=OpenApiTypes.STR,
        required=False,
    ),
    OpenApiParameter(
        name="updated_since",
        location=OpenApiParameter.QUERY,
        description="Return Subjects updated since the given timestamp (ISO8601).",
        type=OpenApiTypes.DATETIME,
        required=False,
    ),
    OpenApiParameter(
        name="position_updated_since",
        location=OpenApiParameter.QUERY,
        description="Return Subjects whose position updated since the given timestamp (ISO8601).",
        type=OpenApiTypes.DATETIME,
        required=False,
    ),
    OpenApiParameter(
        name="render_last_location",
        location=OpenApiParameter.QUERY,
        description="If true, include each subject's last location in the response.",
        type=OpenApiTypes.BOOL,
        required=False,
    ),
    OpenApiParameter(
        name="tracks",
        location=OpenApiParameter.QUERY,
        description="If true, include each subject's recent tracks.",
        type=OpenApiTypes.BOOL,
        required=False,
    ),
    OpenApiParameter(
        name="id",
        location=OpenApiParameter.QUERY,
        description="Comma-delimited list of Subject IDs. Example: 42,43,44",
        type=OpenApiTypes.STR,
        required=False,
    ),
    OpenApiParameter(
        name="subject_subtypes",
        location=OpenApiParameter.QUERY,
        description="Comma-delimited subtype values to filter Subjects.",
        type=OpenApiTypes.STR,
        required=False,
    ),
    OpenApiParameter(
        name="common_name",
        location=OpenApiParameter.QUERY,
        description=("Comma-delimited CommonName values to filter Subjects. " "Example: black_rhino,white_rhino"),
        type=OpenApiTypes.STR,
        required=False,
    ),
    OpenApiParameter(
        name="common_name_search",
        location=OpenApiParameter.QUERY,
        description="Partial (case-insensitive) match on the Subject's common name value.",
        type=OpenApiTypes.STR,
        required=False,
    ),
    OpenApiParameter(
        name="group_name",
        location=OpenApiParameter.QUERY,
        description=(
            "Comma-delimited SubjectGroup names to filter Subjects (matches any listed group). "
            "Example: DCS_Team_Members,BlackRhino. "
            "Note: SubjectGroupsView uses the same parameter name for a single-name "
            "icontains search on group records, not subject membership."
        ),
        type=OpenApiTypes.STR,
        required=False,
    ),
]


@extend_schema_view(
    get=extend_schema(
        parameters=SUBJECTS_LIST_PARAMS,
        summary="List subjects",
        description=(
            "List subjects with optional filters for time, bbox, group, name, "
            "common_name, group_name, and subject_subtypes.\n\n"
            "**JSONField filters (`additional__<key>`):** any query parameter "
            "of the form `additional__<key>=<value>` filters by that key in "
            "Subject.additional (e.g. `additional__sex=male`, "
            "`additional__age=adult`). Multiple keys are ANDed. Reserved "
            "JSONField lookup names (`has_key`, `contains`, `isnull`, etc.) "
            "are rejected. These dynamic parameters are not enumerated in the "
            "schema because their key set is unbounded."
        ),
    )
)
class SubjectsView(ListCreateAPIView, TwoWaySubjectSourceMixin, DynamicSchemaDataMixin):
    """
    get:
    Returns a list of Subject in the system.

    """

    serializer_class = SubjectSerializer
    permission_classes = (SubjectModelPermissions,)
    pagination_class = OptionalResultsSetPagination

    TRACK_QPARAMS = ("tracks_limit",)
    TRACK_DATE_QPARAMS = ("tracks_since", "tracks_until")

    # Ensure this attribute is present with a sensible default for any child
    # classes.
    subject_linked_sources = {}

    window_asc = {
        "partition_by": F("subject_id"),
        "order_by": [
            F("assigned_range").asc(),
        ],
    }
    window_desc = {
        "partition_by": F("subject_id"),
        "order_by": [
            F("assigned_range").desc(),
        ],
    }
    cached_queryset = None
    queryset_linked_user = None
    linked_exists = None

    def check_permissions(self, request):
        if request.user.is_anonymous:
            self.permission_denied(request)

        if self.queryset_linked_user is None:
            self.queryset_linked_user = Subject.objects.filter(linked_user=request.user).distinct("id")

        if self.linked_exists is None:
            self.linked_exists = self.queryset_linked_user.exists()

        if not self.linked_exists:
            super().check_permissions(request)

    def get_queryset(self) -> QuerySet:
        query_params = self.request.query_params
        user = self.request.user

        if self.cached_queryset is not None:
            return self.cached_queryset

        if not (user.has_any_perms(VIEW_SUBJECT_PERMS) or user.has_any_perms(VIEW_SOURCE_PERMS)):
            if self.linked_exists:
                return self.queryset_linked_user
            raise ForbiddenAPIException

        # Apply annotations and additional joins
        use_lkl = parse_bool(query_params.get("use_lkl", False))
        use_bbox = bool(query_params.get("bbox", False))
        min_age_days = get_minimum_allowed_age(user) or 0
        mou_date = user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None

        # Phase 1: Get filtered subject IDs with minimal joins
        base_queryset = Subject.objects.all()

        filtered_queryset = base_queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24, mou_expiry_date=mou_date
        )
        # subjectsource_location is only read by by_bbox_last_known_locations (use_lkl path).
        if use_bbox and use_lkl:
            filtered_queryset = filtered_queryset.annotate_with_subjectsource(use_lkl=use_lkl, use_bbox=use_bbox)

        filtered_queryset = self.filter_on_subject_and_source_groups(filtered_queryset, user, query_params)

        filtered_queryset = self.filter_on_subject_subtype(filtered_queryset, user, query_params)
        filtered_queryset = self.filter_on_common_name(filtered_queryset, query_params)
        filtered_queryset = self.filter_on_group_name(filtered_queryset, query_params)
        filtered_queryset = self.filter_on_additional(filtered_queryset, query_params)
        filtered_queryset = self.filter_on_dates(filtered_queryset, user, query_params)
        filtered_queryset = check_to_include_inactive_subjects(self.request, filtered_queryset)

        # Get the IDs of filtered subjects
        filtered_queryset = filtered_queryset.distinct("id").order_by("id")
        filtered_ids = filtered_queryset.values_list("id", flat=True)

        # Phase 2: Get full data for filtered subjects in chunks to avoid large IN clauses
        CHUNK_SIZE = 1000  # Adjust this based on your database's performance characteristics
        queryset = Subject.objects.none()  # Start with empty queryset

        # Process IDs in chunks
        for i in range(0, len(filtered_ids), CHUNK_SIZE):
            chunk_ids = filtered_ids[i : i + CHUNK_SIZE]
            chunk_queryset = Subject.objects.filter(id__in=chunk_ids)
            chunk_queryset = chunk_queryset.select_related(
                "subject_subtype", "subject_subtype__subject_type", "common_name"
            )
            chunk_queryset = chunk_queryset.annotate_with_subjectstatus(
                delay_hours=min_age_days * 24, mou_expiry_date=mou_date
            ).annotate_with_subjectsource_transforms()
            queryset = queryset.union(chunk_queryset.order_by("id"))

        self._get_two_way_sources(queryset)
        self.cached_queryset = queryset
        return queryset

    def filter_on_subject_and_source_groups(self, filtered_queryset, user, query_params):
        should_include_user_linked_subject = False
        subject_ids = query_params.get("id")
        subject_group_id = query_params.get("subject_group")
        subject_group_param_splited = subject_group_id.split(",") if subject_group_id else []

        should_include_user_linked_subject = not subject_ids and not subject_group_id and self.queryset_linked_user

        filtered_queryset = filtered_queryset.by_user_subjects_not_distinct(
            user, include_linked=should_include_user_linked_subject
        )

        if subject_ids:
            filtered_queryset = filtered_queryset.by_id(subject_ids)
        elif subject_group_id and len(subject_group_param_splited) == 1:
            if not is_uuid(subject_group_id):
                raise ValidationError("Invalid subject_group id at 'subject_group'")

            subject_groups = SubjectGroup.objects.get_nested_groups(parent_id=subject_group_id)
            filtered_queryset = filtered_queryset.by_groups(subject_groups=subject_groups)

        elif subject_group_id and len(subject_group_param_splited) > 1:
            if not all(is_uuid(item.strip()) for item in subject_group_param_splited):
                raise ValidationError("Invalid subject_group id at 'subject_group'")

            filtered_queryset = filtered_queryset.filter(groups__id__in=subject_group_id.split(","))
        else:
            should_include_user_linked_subject = True
            # Fetch all the Subjects whose access is gained through Source Group
            # permissions.
            source_groups = SourceGroup.objects.filter(permission_sets__in=user.get_all_permission_sets())

            subjects_via_source_groups = Subject.objects.filter(subjectsource__source__groups__in=source_groups)
            subjects_via_source_groups = check_to_include_inactive_subjects(self.request, subjects_via_source_groups)
            filtered_queryset |= subjects_via_source_groups

            if not user.is_superuser:
                # TODO: rather than this, can we get the latest & oldest observation for each subject? (needed in
                #  serializer.to_representation)
                subject_linked_sources = (
                    SubjectSource.objects.filter(source__groups__in=source_groups)
                    .annotate(
                        latest_range=Window(expression=FirstValue(F("assigned_range")), **self.window_desc),
                        latest_source=Window(expression=FirstValue(F("source_id")), **self.window_desc),
                        oldest_range=Window(expression=FirstValue(F("assigned_range")), **self.window_asc),
                        oldest_source=Window(expression=FirstValue(F("source_id")), **self.window_asc),
                    )
                    .distinct("subject_id")
                    .values("subject_id", "latest_range", "oldest_range", "latest_source", "oldest_source")
                )

                self.subject_linked_sources = {ss["subject_id"]: ss for ss in subject_linked_sources}

        # Apply name filter
        if name := query_params.get("name"):
            filtered_queryset = filtered_queryset.by_name_search(name)

        return filtered_queryset

    def filter_on_dates(self, queryset, user, query_params):
        """Apply filters that don't require heavy joins"""

        # Apply position filters
        position_updated_since = query_params.get("position_updated_since")
        position_updated_since = dateparse(position_updated_since) if position_updated_since else None

        # Apply update filters
        updated_since = query_params.get("updated_since")
        updated_until = query_params.get("updated_until")
        if position_updated_since and (updated_since or updated_until):
            raise BadRequestAPIException(
                detail="Cannot use both position_updated_since and updated_since/updated_until"
            )

        if position_updated_since:
            logger.info("position_updated_since: %s", position_updated_since)
            queryset = queryset.by_position_updated_since(position_updated_since)

        is_updated_since_valid, updated_since = check_valid_date_string(updated_since, "updated_since")
        is_updated_until_valid, updated_until = check_valid_date_string(updated_until, "updated_until")

        if is_updated_since_valid and is_updated_until_valid:
            queryset = queryset.by_updated_since_until(updated_since, updated_until)
        elif is_updated_since_valid:
            queryset = queryset.by_updated_since(updated_since)
            updated_until = None
        elif is_updated_until_valid:
            queryset = queryset.by_updated_until(updated_until)
            updated_since = None
        else:
            updated_since = None
            updated_until = None

        return self.filter_on_location(
            queryset=queryset,
            user=user,
            query_params=query_params,
            position_updated_since=position_updated_since,
            updated_since=updated_since,
            updated_until=updated_until,
        )

    def filter_on_subject_subtype(self, queryset, user, query_params):
        # Apply subject type filters
        if subtype_values := query_params.get("subject_subtypes"):
            subtype_values_list = subtype_values.split(",")
            queryset = queryset.filter(subject_subtype__value__in=subtype_values_list)

        return queryset

    def filter_on_common_name(self, queryset: QuerySet, query_params) -> QuerySet:
        """Filter by CommonName value (exact) or partial match (case-insensitive).

        CommonName.value is the FK primary key, so common_name__value lookups
        do not actually join the CommonName table; Django collapses them to
        the FK column on Subject.
        """
        if common_names := query_params.get("common_name"):
            values = [v.strip() for v in common_names.split(",") if v.strip()]
            queryset = queryset.filter(common_name__value__in=values)

        if search := query_params.get("common_name_search"):
            queryset = queryset.filter(common_name__value__icontains=search.strip())

        return queryset

    def filter_on_group_name(self, queryset: QuerySet, query_params) -> QuerySet:
        """Filter by SubjectGroup name(s)."""
        if group_names := query_params.get("group_name"):
            names_list = [v.strip() for v in group_names.split(",")]
            queryset = queryset.filter(groups__name__in=names_list)

        return queryset

    _ADDITIONAL_KEY_PATTERN = re.compile(r"^additional__([a-zA-Z_][a-zA-Z0-9_]*)$")
    _JSONFIELD_RESERVED_LOOKUPS = frozenset(
        {
            "contains",
            "contained_by",
            "has_key",
            "has_keys",
            "has_any_keys",
            "icontains",
            "iexact",
            "iendswith",
            "istartswith",
            "isnull",
            "overlap",
            "regex",
            "iregex",
        }
    )

    def filter_on_additional(self, queryset: QuerySet, query_params) -> QuerySet:
        """Filter by keys in the Subject.additional JSONField.

        Accepts query parameters ``additional__<key>=<value>`` where ``<key>`` is
        a JSON object key (not a Django JSONField lookup name).
        """
        additional_filters: dict[str, str] = {}
        for param in query_params:
            match = self._ADDITIONAL_KEY_PATTERN.match(param)
            if not match:
                continue
            json_key = match.group(1)
            if json_key in self._JSONFIELD_RESERVED_LOOKUPS:
                continue
            additional_filters[f"additional__{json_key}"] = query_params[param]

        if additional_filters:
            queryset = queryset.filter(**additional_filters)

        return queryset

    def filter_on_location(self, queryset, user, query_params, position_updated_since, updated_since, updated_until):
        # Apply bbox filter if present
        if bbox := query_params.get("bbox"):
            bbox_values = [float(v) for v in bbox.split(",")]
            if len(bbox_values) != 4:
                raise ValueError("invalid bbox param")

            show_stationary_subjects = get_tenant_settings().env_settings.show_stationary_subjects_on_map
            last_days = get_track_days()

            if parse_bool(query_params.get("use_lkl")):
                queryset = queryset.by_bbox_last_known_locations(
                    bbox_values,
                    last_days=last_days,
                    include_stationary_subjects=show_stationary_subjects,
                    updated_since=position_updated_since or updated_since,
                    updated_until=updated_until,
                )
            else:
                queryset = queryset.by_bbox(
                    bbox_values,
                    last_days=last_days,
                    include_stationary_subjects=show_stationary_subjects,
                    updated_since=position_updated_since or updated_since,
                    updated_until=updated_until,
                )

        return queryset

    def get_serializer_context(self):
        request = self.request
        query_params = request.query_params

        context = super().get_serializer_context()
        context["render_last_location"] = parse_bool(query_params.get("render_last_location", True))
        render_tracks = parse_bool(query_params.get("tracks", False))
        context["tracks"] = render_tracks
        context["subject_linked_sources"] = self.subject_linked_sources
        context["two_way_subject_sources"] = self.two_way_subject_sources

        if request and render_tracks:
            for track_param in self.TRACK_QPARAMS:
                context[track_param] = query_params.get(track_param, None)
            for track_param in self.TRACK_DATE_QPARAMS:
                context[track_param] = (
                    dateparse(query_params.get(track_param, None)) if query_params.get(track_param, None) else None
                )
        return context

    def create(self, request, *args, **kwargs):
        many = True if isinstance(request.data, list) else False

        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class SubjectsGeoJsonView(SubjectsView):
    serializer_class = SubjectGeoJsonSerializer
    pagination_class = StandardResultsSetGeoJsonPagination
    renderer_classes = (ExtendedGEOJSONRenderer,)


class SubjectView(RetrieveUpdateDestroyAPIView, TwoWaySubjectSourceMixin):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = SubjectSerializer
    lookup_field = "id"

    def check_permissions(self, request):
        subject_id = self.kwargs.get("id")
        self.queryset_linked_user = Subject.objects.filter(linked_user=request.user, id=subject_id)
        if not self.queryset_linked_user.exists():
            for permission in self.get_permissions():
                if not permission.has_permission(request, self):
                    self.permission_denied(request)

    def get_queryset(self):
        subject_id = self.kwargs.get("id")
        subject = get_object_or_404(Subject.objects.all(), pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise ForbiddenAPIException
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = Subject.objects.filter(id=subject_id)
        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24, mou_expiry_date=mou_date
        ).annotate_with_subjectsource_transforms()
        self._get_two_way_sources(queryset)
        return queryset

    def get_object(self):
        if self.queryset_linked_user.exists():
            subject_id = self.kwargs.get("id")
            return get_object_or_404(self.queryset_linked_user, pk=subject_id)
        return super().get_object()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["two_way_subject_sources"] = self.two_way_subject_sources

        return context

    def patch(self, request, *args, **kwargs):
        subject_id = self.kwargs["id"]
        if "id" in request.data and request.data["id"] != subject_id:
            raise BadRequestAPIException(detail="id in patch request does not match subject_id")
        return super().patch(request, *args, **kwargs)


class SubjectGroupsView(ListAPIView, TwoWaySubjectSourceMixin):
    """
    Returns all subjectgroups in the system.
    """

    serializer_class = AllGroupsSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (create_gp_filter_class("subjectgf", ("observations.view_subjectgroup",), SubjectGroup),)
    schema = SubjectGroupsViewSchema()

    @etag(all_group_subjects_etag)
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        qparams = request.query_params
        include_subgroups = not parse_bool(qparams.get("flat"))

        user = getattr(request, "user", None)
        include_inactive = qparams.get("include_inactive")
        mou_date = user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None

        mounted_hierarchy, related_sujects_ids = build_groups_hierarchy_with_all_subjects(
            queryset, user, include_inactive, mou_date, include_subgroups
        )
        self._get_two_way_sources_by_subject_ids(related_sujects_ids)
        serializer = AllGroupsSerializer(mounted_hierarchy, context=self.get_serializer_context(), many=True)

        return Response(serializer.data)

    def get_queryset(self):
        queryset = SubjectGroupGetQuerySet().get_all_queryset()

        if group_name := self.request.query_params.get("group_name"):
            queryset = queryset.by_name_search(group_name)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        query_params = self.request.query_params
        context["render_last_location"] = parse_bool(query_params.get("render_last_location", True))
        context["request"] = self.request
        context["two_way_subject_sources"] = self.two_way_subject_sources
        context["show_track_days_since"] = default_since()
        return context


class SubjectGroupSubjectsMixin(TwoWaySubjectSourceMixin):
    """Mixin to provide shared functionality for getting subjects from a subject group."""

    def get_serializer_context(self):
        context = super().get_serializer_context()
        query_params = self.request.query_params
        context["render_last_location"] = parse_bool(query_params.get("render_last_location", True))
        context["two_way_subject_sources"] = self.two_way_subject_sources
        return context

    def get_subjects_from_group(self, subject_group_id):
        """Shared method to get subjects from a subject group with proper annotations."""
        subject_group = get_object_or_404(SubjectGroup.objects.all(), pk=subject_group_id)

        # Check permissions on the subject group
        if not self.request.user.has_any_perms(("observations.view_subjectgroup",), subject_group):
            raise ForbiddenAPIException

        queryset = subject_group.subjects.all()

        # Apply the same annotations as the main subjects view
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None

        queryset = queryset.select_related("subject_subtype", "subject_subtype__subject_type", "common_name")
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24, mou_expiry_date=mou_date
        ).annotate_with_subjectsource_transforms()

        self._get_two_way_sources(queryset)
        return queryset


class SubjectGroupSubjectsView(SubjectGroupSubjectsMixin, ListAPIView):
    """
    Manage subjects within a specific subject group.

    GET: Returns all subjects in the group
    POST: Add subjects to the group
    """

    serializer_class = SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = OptionalResultsSetPagination
    lookup_field = "id"

    def get_queryset(self):
        """Get subjects that belong to the specified subject group."""
        return self.get_subjects_from_group(self.kwargs.get("id"))

    def post(self, request, *args, **kwargs):
        """
        Add one or more subjects to the subject group.

        Expected payload:
        [
            {"id": "uuid1"}, {"id": "uuid2"}, ...
        ]
        """
        subject_group_id = self.kwargs.get("id")
        subject_group = get_object_or_404(SubjectGroup.objects.all(), pk=subject_group_id)

        # Check permissions on the subject group
        if not self.request.user.has_any_perms(("observations.change_subjectgroup",), subject_group):
            raise ForbiddenAPIException

        # Validate the request data
        serializer = SubjectIdSerializer(data=request.data, context={"request": request}, many=True)
        serializer.is_valid(raise_exception=True)

        # Extract subject IDs from the validated subjects array
        validated_data = serializer.validated_data
        subject_ids = [item["id"] for item in validated_data]

        # Get the subjects
        subjects = Subject.objects.filter(id__in=subject_ids)

        # Add subjects to the group
        try:
            subject_group.subjects.add(*subjects)
        except IntegrityError:
            # Handle case where subjects might already be in the group
            return return_409_response(message="Some subjects may already be in this group.")

        # Return the updated subject list (same as GET)
        queryset = self.get_subjects_from_group(subject_group_id)
        serializer = self.get_serializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        """
        Remove one or more subjects from the subject group.

        Expected payload:
        [
            {"id": "uuid1"}, {"id": "uuid2"}, ...
        ]
        """
        subject_group_id = self.kwargs.get("id")
        subject_group = get_object_or_404(SubjectGroup.objects.all(), pk=subject_group_id)

        # Check permissions on the subject group
        if not self.request.user.has_any_perms(("observations.change_subjectgroup",), subject_group):
            raise ForbiddenAPIException

        # Validate the request data
        serializer = SubjectIdSerializer(data=request.data, context={"request": request}, many=True)
        serializer.is_valid(raise_exception=True)

        # Extract subject IDs from the validated subjects array
        subject_ids = [item["id"] for item in serializer.validated_data]

        # Remove the subjects from the group
        subjects = Subject.objects.filter(id__in=subject_ids)
        subject_group.subjects.remove(*subjects)

        # Return the updated subject list (same as GET)
        queryset = self.get_subjects_from_group(subject_group_id)
        serializer = self.get_serializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)


class SubjectGroupView(SubjectGroupSubjectsMixin, RetrieveAPIView):
    """
    Returns a single SubjectGroup
    """

    serializer_class = create_sg_serializer("subjectgs", SubjectGroup, SubjectSerializer)
    permission_classes = (StandardObjectPermissions,)
    lookup_field = "id"
    filter_backends = (create_gp_filter_class("subjectgf", ("observations.view_subjectgroup",), SubjectGroup),)

    def get_queryset(self):
        queryset = SubjectGroup.objects.get_non_cyclic_subjectgroups(single_sg=True)
        queryset.order_by("name")
        self._get_two_way_sources(queryset)
        return queryset

    @etag(subject_group_etag)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
