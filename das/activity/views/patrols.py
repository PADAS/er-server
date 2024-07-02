import copy
import json
import logging
import mimetypes

import versatileimagefield.files
from rest_framework_condition import condition

from django.db.models import CharField, Prefetch, Q
from django.db.models.functions import Cast
from django.db.utils import IntegrityError
from django.http import HttpResponse
from rest_framework import status
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveAPIView,
    RetrieveUpdateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.response import Response

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
    PatrolTypeSerializer,
)
from activity.views.helpers import get_segments
from observations.models import Subject
from usercontent.serializers import get_stored_filename
from utils.drf import StandardResultsSetPagination, return_409_response

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

        # TODO: This conditional is to handle the case where a file is uploaded
        # via XHR. Figure out why.
        if "filecontent.file" not in request.data:
            try:
                # Ajax request.
                request.data["filecontent.file"] = request.stream.FILES["filecontent.file"]
            except KeyError:
                return Response("filecontent.file not found", status=status.HTTP_400_BAD_REQUEST)

        this_data = copy.copy(request.data)
        this_data["patrol"] = patrol

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


class PatrolTypeView(RetrieveAPIView):
    lookup_field = "id"
    serializer_class = PatrolTypeSerializer
    permission_classes = (PatrolTypePermissions,)

    def get_queryset(self):
        return PatrolType.objects.all()

    @condition(etag_func=build_patrol_type_etag_header, last_modified_func=build_patrol_type_last_modified_header)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PatrolTypesView(ListAPIView):
    serializer_class = PatrolTypeSerializer
    permission_classes = (PatrolTypePermissions,)

    def get_queryset(self):
        return PatrolType.objects.all()

    @condition(etag_func=build_patrol_types_etag_header, last_modified_func=build_patrol_types_last_modified_header)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PatrolView(RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    serializer_class = PatrolSerializer
    permission_classes = (PatrolObjectPermissions,)

    def get_queryset(self):
        return Patrol.objects.all()


class PatrolsView(ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    serializer_class = PatrolSerializer
    permission_classes = (PatrolObjectPermissions,)
    schema = PatrolSchema()

    def post(self, request, *args, **kwargs):
        try:
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

        queryset = self._filter_by_viewable_subjects(queryset)

        queryset = queryset.prefetch_related(
            "notes", "files", "patrol_segments__patrol_type", "patrol_segments__events"
        )

        return queryset.sort_patrols()

    def _filter_by_viewable_subjects(self, queryset):
        user = self.request.user
        user_model_name = user._meta.model_name
        viewable_patrol_subjects = Subject.objects.by_user_subjects_and_linked(user).values_list("id", flat=True)
        return queryset.filter(
            Q(patrol_segment__leader_id=None)
            | (
                Q(patrol_segment__leader_id__in=viewable_patrol_subjects)
                & Q(patrol_segment__leader_content_type__model="subject")
            )
            | Q(patrol_segment__leader_content_type__model=user_model_name)
        )


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
        queryset = PatrolSegment.objects.select_related("patrol_type", "patrol").all()
        queryset.prefetch_related(Prefetch("events"), Prefetch("eventrelatedsegments_set"))
        return get_segments(self.kwargs, queryset)
