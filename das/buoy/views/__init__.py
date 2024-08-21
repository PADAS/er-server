import datetime
import logging

from django.db.models import F, Window
from django.db.models.functions import FirstValue
from django.db.utils import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response

from buoy.serializers import GearSerializer
from observations import Subject, models
from observations.permissions import StandardObjectPermissions
from observations.utils import (
    VIEW_SUBJECT_PERMS,
    check_to_include_inactive_subjects,
    dateparse,
    get_minimum_allowed_age,
)
from observations.views.helpers import check_valid_date_string
from utils.drf import (
    ForbiddenAPIException,
    OptionalResultsSetPagination,
    return_409_response,
)
from utils.json import parse_bool
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)


def get_track_days():
    show_track_days = get_tenant_settings().env_settings.show_track_days
    return datetime.timedelta(days=int(show_track_days))


class GearView(generics.ListCreateAPIView):
    """
    get:
    Returns a list of Gear in the system.

    """

    serializer_class = GearSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = OptionalResultsSetPagination

    TRACK_QPARAMS = ("tracks_limit",)
    TRACK_DATE_QPARAMS = ("tracks_since", "tracks_until")

    # TODO: Create GearViewSchema
    schema = GearViewSchema()

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

    def check_permissions(self, request):
        if request.user.is_anonymous:
            self.permission_denied(request)
        self.queryset_linked_user = Subject.objects.filter(linked_user=request.user).distinct()
        if not self.queryset_linked_user.exists():
            for permission in self.get_permissions():
                if not permission.has_permission(request, self):
                    self.permission_denied(request)

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS) and self.queryset_linked_user.exists():
            return self.queryset_linked_user
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS):
            raise ForbiddenAPIException

        subject_group = self.request.query_params.get("subject_group")
        subject_ids = self.request.query_params.get("id")

        # Apply request query filters that have are compatible with any of the
        # criteria above.
        updated_since = self.request.query_params.get("updated_since")
        name = self.request.query_params.get("name", None)
        self.request.query_params.get("lat", None)
        self.request.query_params.get("lon", None)
        state = self.request.query_params.get("state", None)

        # Question: What are these?
        use_last_known_location = parse_bool(self.request.query_params.get("use_lkl"))
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None

        queryset = Subject.objects.all()

        # need a stable sort for pagination. this needs to match the distinct
        # parameter set in by_user_subjects
        if state == "hauled":
            queryset = check_to_include_inactive_subjects(self.request, queryset)
        queryset = queryset.order_by("id")

        # Question: What is this? And line 98
        queryset = queryset.by_user_subjects(self.request.user)

        queryset = queryset.select_related("subject_subtype", "subject_subtype__subject_type", "common_name")

        if subject_ids:
            queryset = queryset.by_id(subject_ids)
        else:
            # Fetch all the Subjects whose access is gained through Source Group
            # permissions.
            source_groups = models.SourceGroup.objects.filter(
                permission_sets__in=self.request.user.get_all_permission_sets()
            )

            subjects_via_source_groups = Subject.objects.filter(subjectsource__source__groups__in=source_groups)
            subjects_via_source_groups = check_to_include_inactive_subjects(self.request, subjects_via_source_groups)
            queryset = queryset.distinct() | subjects_via_source_groups.distinct()

            if not self.request.user.is_superuser:
                # TODO: rather than this, can we get the latest & oldest observation for each subject? (needed in
                #  serializer.to_representation)
                subject_linked_sources = (
                    models.SubjectSource.objects.filter(source__groups__in=source_groups)
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

            self._get_two_way_sources(queryset)

        is_updated_since_valid, updated_since = check_valid_date_string(updated_since, "updated_since")
        is_updated_until_valid, updated_until = check_valid_date_string(updated_until, "updated_until")

        queryset = queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
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

        # TODO: query by location
        if bbox:
            bbox = bbox.split(",")
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            show_stationary_subjects_on_map = get_tenant_settings().env_settings.show_stationary_subjects_on_map
            # Question: What is this?
            if use_last_known_location:
                queryset = queryset.by_bbox_last_known_locations(
                    bbox,
                    last_days=get_track_days(),
                    include_stationary_subjects=show_stationary_subjects_on_map,
                    updated_since=updated_since,
                    updated_until=updated_until,
                )
            else:
                queryset = queryset.by_bbox(
                    bbox,
                    last_days=get_track_days(),
                    include_stationary_subjects=show_stationary_subjects_on_map,
                    updated_since=updated_since,
                    updated_until=updated_until,
                )

        # Remove this if query parameter not available?
        if name:
            queryset = queryset.by_name_search(self.request.query_params.get("name"))

        # What is this?
        if (
            not name
            and not subject_group
            and not subject_ids
            and self.queryset_linked_user
            and not queryset.filter(id=self.queryset_linked_user.first().id).exists()
        ):
            queryset = queryset.union(
                self.queryset_linked_user.select_related(
                    "subject_subtype", "subject_subtype__subject_type", "common_name"
                ).annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
            )
        return queryset

    def get_serializer_context(self):
        request = self.request
        context = super().get_serializer_context()
        context["render_last_location"] = True
        context["tracks"] = False
        context["subject_linked_sources"] = self.subject_linked_sources
        context["two_way_subject_sources"] = self.two_way_subject_sources

        if request and parse_bool(request.query_params.get("tracks", None)):
            context["tracks"] = True
            for t in self.TRACK_QPARAMS:
                context[t] = request.query_params.get(t, None)
            for t in self.TRACK_DATE_QPARAMS:
                context[t] = dateparse(request.query_params.get(t, None)) if request.query_params.get(t, None) else None
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


class SingleGearView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = GearSerializer
    lookup_field = "id"

    def check_permissions(self, request):
        subject_id = self.kwargs.get("id")
        self.queryset_linked_user = models.Subject.objects.filter(linked_user=request.user, id=subject_id)
        if not self.queryset_linked_user.exists():
            for permission in self.get_permissions():
                if not permission.has_permission(request, self):
                    self.permission_denied(request)

    def get_queryset(self):
        subject_id = self.kwargs.get("id")
        subject = generics.get_object_or_404(models.Subject.objects.all(), pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise ForbiddenAPIException
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = models.Subject.objects.filter(id=subject_id)
        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None
        queryset = queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
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
