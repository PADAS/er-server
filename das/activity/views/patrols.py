from __future__ import annotations

import copy
import json
import logging
import mimetypes
from typing import NoReturn

import versatileimagefield.files
from rest_framework_condition import condition

from django.db import transaction
from django.db.models import CharField, Exists, OuterRef, Prefetch, Q, QuerySet
from django.db.models.functions import Cast
from django.db.utils import IntegrityError
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from activity.libs.constants import ActivityConstants
from activity.models import (
    Patrol,
    PatrolFile,
    PatrolNote,
    PatrolSegment,
    PatrolType,
    StateFilters,
)
from activity.permissions import PatrolObjectPermissions, PatrolTypePermissions
from activity.serializers import (
    PatrolFileSerializer,
    PatrolNoteSerializer,
    PatrolSegmentSerializer,
    PatrolSerializer,
    PatrolTypeCRUDSerializer,
)
from activity.views.helpers import get_segments
from observations.models import Subject
from usercontent.serializers import get_stored_filename
from utils.drf import (
    StandardResultsSetCursorPagination,
    StandardResultsSetPagination,
    apply_deprecation_headers,
    return_409_response,
)
from utils.json import parse_bool

from .response_headers import (
    build_patrol_type_etag_header,
    build_patrol_type_last_modified_header,
    build_patrol_types_etag_header,
    build_patrol_types_last_modified_header,
)
from .schemas import PatrolSchema

logger = logging.getLogger(__name__)


class PatrolFileView(RetrieveUpdateDestroyAPIView):
    permission_classes = (PatrolObjectPermissions,)
    serializer_class = PatrolFileSerializer

    def get_queryset(self):
        return PatrolFile.objects.all().filter(patrol=get_object_or_404(Patrol.objects.all(), pk=self.kwargs.get("id")))

    def get_object(self):
        queryset = self.get_queryset()
        filters = {"id": self.kwargs["filecontent_id"]}

        obj = get_object_or_404(queryset, **filters)
        return obj

    def get(self, request, *args, **kwargs):
        if self.kwargs.get("filename", None) == "meta-data":
            return super().get(request, *args, **kwargs)

        instance = self.get_object()

        desired_image_size = self.kwargs.get("image_size", None)
        content_type, encoding = mimetypes.guess_type(instance.usercontent.filename)

        if content_type in ActivityConstants.USERCONTENT_FORCE_DOWNLOAD:
            content_type = "application/octet-stream"

        if isinstance(
            instance.usercontent.file,
            (versatileimagefield.files.VersatileImageFieldFile,),
        ):
            filename = get_stored_filename(
                instance.usercontent.file,
                rendition_set="default",
                rendition_key=desired_image_size,
            )
            try:
                response_file = instance.usercontent.file.field.storage.open(filename)
            except OSError:
                logger.warning(
                    "Failed attempt to open file %s. Will default to original file version.",
                    filename,
                )
                response_file = instance.usercontent.file

            response = HttpResponse(response_file, content_type=content_type)
        else:
            response = HttpResponse(instance.usercontent.file, content_type=content_type)
            response["Content-Disposition"] = "attachment; filename=%s" % instance.usercontent.filename

        return response


class PatrolFilesView(ListCreateAPIView):
    permission_classes = (PatrolObjectPermissions,)
    serializer_class = PatrolFileSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        patrol = self.get_patrol()

        this_data = copy.copy(request.data)
        this_data["patrol"] = patrol

        if "usercontent_id" not in request.data:
            # Legacy path: inline file upload (direct POST or XHR multipart).
            # TODO: This conditional is to handle the case where a file is uploaded
            # via XHR. Figure out why.
            if "filecontent.file" not in request.data:
                try:
                    # Ajax request.
                    request.data["filecontent.file"] = request.stream.FILES["filecontent.file"]
                except KeyError:
                    return Response("filecontent.file not found", status=status.HTTP_400_BAD_REQUEST)
            this_data["usercontent.file"] = this_data["filecontent.file"]

        serializer = self.get_serializer(data=this_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        return self.get_patrol().files.all()

    def get_patrol(self):
        return get_object_or_404(Patrol.objects.all(), pk=self.kwargs.get("id"))


class PatrolNoteView(RetrieveUpdateAPIView):
    permission_classes = (PatrolObjectPermissions,)
    serializer_class = PatrolNoteSerializer

    def get_queryset(self):
        notes = PatrolNote.objects.all().filter(patrol=self.get_patrol())
        return notes

    def get_object(self):
        queryset = self.get_queryset()
        filters = {"id": self.kwargs["note_id"]}

        obj = get_object_or_404(queryset, **filters)

        return obj

    def get_patrol(self):
        return get_object_or_404(Patrol.objects.all(), pk=self.kwargs.get("id"))


class PatrolNotesView(ListCreateAPIView):
    permission_classes = (PatrolObjectPermissions,)
    serializer_class = PatrolNoteSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):
        request.data["patrol"] = self.get_patrol()
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        return PatrolNote.objects.all().filter(patrol=self.get_patrol())

    def get_patrol(self):
        return get_object_or_404(Patrol.objects.all(), pk=self.kwargs.get("id"))


class PatrolTypeViewSet(ModelViewSet):
    permission_classes = (PatrolTypePermissions,)
    serializer_class = PatrolTypeCRUDSerializer
    lookup_field = "id"
    queryset = PatrolType.objects.none()

    def get_queryset(self) -> QuerySet[PatrolType]:
        return PatrolType.objects.all().order_by("ordernum", "display")

    _VALUE_CONSTRAINT = "activity_patroltype_unique_value_across_tenants"

    def _handle_integrity_error(self, exc: IntegrityError) -> NoReturn:
        if self._VALUE_CONSTRAINT in str(exc):
            raise ValidationError({"value": "A patrol type with this value already exists."})
        raise exc

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            self._handle_integrity_error(exc)

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        try:
            with transaction.atomic():
                return super().update(request, *args, **kwargs)
        except IntegrityError as exc:
            self._handle_integrity_error(exc)

    @condition(etag_func=build_patrol_types_etag_header, last_modified_func=build_patrol_types_last_modified_header)
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().list(request, *args, **kwargs)

    @condition(etag_func=build_patrol_type_etag_header, last_modified_func=build_patrol_type_last_modified_header)
    def retrieve(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().retrieve(request, *args, **kwargs)


class PatrolView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    serializer_class = PatrolSerializer
    permission_classes = (PatrolObjectPermissions,)

    def get_queryset(self):
        return Patrol.objects.all()


class PatrolsCursorPagination(StandardResultsSetCursorPagination):
    ordering = "-serial_number"

    def decode_cursor(self, request):
        """Decode the cursor, turning a tampered/garbage position into a 404.

        DRF's ``CursorPagination.decode_cursor`` already raises ``NotFound`` for a
        malformed encoding or an out-of-range offset, but it does not validate the
        ordering ``position`` component. Because this paginator orders by the integer
        ``serial_number`` field, a tampered non-integer position would flow into the
        SQL comparison and surface as a 500. Int-validate the position here — but only
        when it is non-None, since DRF 3.16 legitimately emits offset-only cursors
        with ``position=None``.
        """
        cursor = super().decode_cursor(request)
        if cursor is not None and cursor.position is not None:
            try:
                int(cursor.position)
            except (TypeError, ValueError):
                raise NotFound(self.invalid_cursor_message)
        return cursor


class PatrolsView(ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    serializer_class = PatrolSerializer
    permission_classes = (PatrolObjectPermissions,)
    schema = PatrolSchema()

    def _use_cursor(self) -> bool:
        return parse_bool(self.request.query_params.get("use_cursor"))

    @property
    def paginator(self):
        """The paginator instance associated with the view, or ``None``.

        API callers can opt into a cursor-based paginator (ordered by
        ``-serial_number``) by passing ``use_cursor=true``; otherwise the
        default page-number paginator is used.
        """
        if not hasattr(self, "_paginator"):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = PatrolsCursorPagination() if self._use_cursor() else self.pagination_class()
        return self._paginator

    def finalize_response(self, request: Request, response: Response, *args, **kwargs) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        # Page-based pagination is the deprecated default, but only for the GET
        # list. POST (patrol creation) and other methods are not deprecated, so
        # don't flag them. Skip when the caller opted into the cursor paginator.
        if request.method == "GET" and not self._use_cursor():
            apply_deprecation_headers(response)
        return response

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().post(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

    def get(self, request, *args, **kwargs):
        state_filters = self.request.query_params.getlist("status", None)
        if state_filters:
            allowed_state_filters = [state.value for state in StateFilters]
            for state in state_filters:
                if state not in allowed_state_filters:
                    return Response(
                        data={"error": f'Only states: {", ".join(allowed_state_filters)} allowed for filtering'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Patrol.objects.all().annotate(serial_number_string=Cast("serial_number", CharField()))
        query_params = self.request.query_params
        patrol_filter = query_params.get("filter")
        exclude_empty_patrols = parse_bool(query_params.get("exclude_empty_patrols", False))

        if patrol_filter:
            try:
                patrol_filter = json.loads(patrol_filter)
                queryset = queryset.by_patrol_filter(patrol_filter)
            except json.JSONDecodeError:
                logger.exception("Invalid filter expression. filter=%s", patrol_filter)
                raise

        if query_params.getlist("status", None):
            states = query_params.getlist("status")
            queryset = queryset.by_state(states)

        if exclude_empty_patrols:
            queryset = queryset.exclude_patrols_without_segments()

        queryset = self._filter_by_viewable_subjects(queryset)

        queryset = queryset.prefetch_related(
            "notes", "files", "patrol_segments__patrol_type", "patrol_segments__events"
        )

        if self._use_cursor():
            # The cursor paginator orders by -serial_number and cannot page over
            # NULL serial numbers, so exclude them. We also skip the expensive
            # sort_patrols() annotate/order_by — the paginator supplies its own
            # ordering, and dropping it lets us avoid the COUNT and the segment
            # subqueries that page-number pagination needs for display ordering.
            return queryset.exclude(serial_number__isnull=True)

        return queryset.sort_patrols()

    def _filter_by_viewable_subjects(self, queryset):
        user = self.request.user
        user_model_name = user._meta.model_name
        viewable_patrol_subjects = Subject.objects.by_user_subjects_and_linked(user).values_list("id", flat=True)
        # A patrol is viewable if it has a segment whose leader is null, a viewable
        # subject, or a user. Expressed as a single correlated Exists() subquery so
        # the multi-valued patrol_segment relation is matched at most once instead of
        # joined repeatedly.
        #
        # The previous implementation used a LEFT OUTER JOIN with Q(patrol_segment__leader_id=None);
        # that also matched patrols with NO segments at all (the join produced an all-null row).
        # Preserve that behaviour: a patrol with no segments is viewable.
        has_any_segment = Exists(PatrolSegment.objects.filter(patrol=OuterRef("pk")))
        viewable_segment = Exists(
            PatrolSegment.objects.filter(patrol=OuterRef("pk")).filter(
                Q(leader_id=None)
                | (Q(leader_id__in=viewable_patrol_subjects) & Q(leader_content_type__model="subject"))
                | Q(leader_content_type__model=user_model_name)
            )
        )
        return queryset.filter(Q(viewable_segment) | ~Q(has_any_segment))


class PatrolSegmentView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    permission_classes = (PatrolObjectPermissions,)
    serializer_class = PatrolSegmentSerializer

    def get_queryset(self):
        queryset = (
            PatrolSegment.objects.select_related("patrol_type", "patrol")
            .prefetch_related(Prefetch("events"), Prefetch("eventrelatedsegments_set"))
            .filter(id=self.kwargs.get("id"))
        )
        return get_segments(self.kwargs, queryset)


class PatrolSegmentsView(ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    serializer_class = PatrolSegmentSerializer
    permission_classes = (PatrolObjectPermissions,)

    def get_queryset(self):
        queryset = PatrolSegment.objects.select_related("patrol_type", "patrol").all().order_by("time_range")
        queryset = queryset.prefetch_related(Prefetch("events"), Prefetch("eventrelatedsegments_set"))
        return get_segments(self.kwargs, queryset)
