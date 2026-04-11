import copy
import logging
import mimetypes

import versatileimagefield.files

from django.http import HttpResponse
from rest_framework import status
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.response import Response

from activity.libs.constants import ActivityConstants
from activity.models import Event, EventFile
from activity.permissions import EventCategoryGeographicPermission
from activity.serializers import EventFileSerializer
from usercontent.serializers import get_stored_filename
from utils.drf import StandardResultsSetPagination

logger = logging.getLogger(__name__)


class EventFileView(RetrieveUpdateDestroyAPIView):
    permission_classes = (EventCategoryGeographicPermission,)
    serializer_class = EventFileSerializer

    def get_queryset(self):
        event = get_object_or_404(Event.objects.all(), pk=self.kwargs.get("event_id"))

        qs = EventFile.objects.all().filter(event=event)
        return qs

    def get_object(self):
        queryset = self.get_queryset()
        filters = {"id": self.kwargs["filecontent_id"]}

        obj = get_object_or_404(queryset, **filters)
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request, *args, **kwargs):

        # if request.GET.get('data', 'false').lower() == 'true':
        if self.kwargs.get("filename", None) == "meta-data":
            return super().get(request, *args, **kwargs)

        instance = self.get_object()

        desired_image_size = self.kwargs.get("image_size", None)
        content_type, encoding = mimetypes.guess_type(instance.usercontent.filename)

        if content_type in ActivityConstants.USERCONTENT_FORCE_DOWNLOAD:
            content_type = "application/octet-stream"

        if isinstance(instance.usercontent.file, (versatileimagefield.files.VersatileImageFieldFile,)):
            filename = get_stored_filename(
                instance.usercontent.file, rendition_set="default", rendition_key=desired_image_size
            )
            try:
                response_file = instance.usercontent.file.field.storage.open(filename)
            except OSError:
                logger.warning("Failed attempt to open file %s. Will default to original file version.", filename)
                response_file = instance.usercontent.file

            response = HttpResponse(response_file, content_type=content_type)
        else:
            response = HttpResponse(instance.usercontent.file, content_type=content_type)
            response["Content-Disposition"] = "attachment; filename=%s" % instance.usercontent.filename

        return response


class EventFilesView(ListCreateAPIView):
    permission_classes = (EventCategoryGeographicPermission,)
    serializer_class = EventFileSerializer
    pagination_class = StandardResultsSetPagination

    def create(self, request, *args, **kwargs):

        event = get_object_or_404(Event.objects.all(), pk=self.kwargs["id"])

        this_data = copy.copy(request.data)
        this_data["event"] = event.id

        if "usercontent_id" not in request.data:
            # Legacy path: inline file upload (direct POST or XHR multipart).
            # TODO: This conditional is to handle the case where a file is uploaded
            # via XHR. Figure out why.
            if "filecontent.file" not in request.data:
                try:
                    # Ajax request.
                    request.data["filecontent.file"] = request.stream.FILES["filecontent.file"]
                except KeyError:
                    pass
            this_data["usercontent.file"] = this_data["filecontent.file"]

        serializer = self.get_serializer(data=this_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_queryset(self):
        event = get_object_or_404(Event.objects.all(), pk=self.kwargs.get("id"))

        return event.files.all()
