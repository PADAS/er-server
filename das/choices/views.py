from django_filters import rest_framework as filters

from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from rest_framework import generics
from rest_framework.filters import OrderingFilter
from rest_framework.views import APIView

from choices.filters import ChoicesFilterSet
from choices.models import Choice
from choices.permissions import ChoiceModelPermissions
from choices.serializers import ChoiceIconZipSerializer, ChoiceSerializer
from utils.drf import StandardResultsSetPagination, return_409_response
from utils.helpers import FileCompression


class ChoiceZipIcon(APIView):
    def get(self, request):
        choices = Choice.objects.values("icon").exclude(Q(icon__exact="") | Q(icon__exact=None)).distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        if serializer.data == []:
            raise Http404()

        file_compress = FileCompression(serializer.data)
        return file_compress.zip_compress("choice_icons")


class ChoicesView(generics.ListCreateAPIView):
    permission_classes = (ChoiceModelPermissions,)
    filter_backends = [filters.DjangoFilterBackend, OrderingFilter]
    filterset_class = ChoicesFilterSet
    serializer_class = ChoiceSerializer
    pagination_class = StandardResultsSetPagination
    ordering_fields = ("ordernum", "value", "display")
    ordering = ("ordernum", "value")

    def get_queryset(self):
        return Choice.objects.all()

    def post(self, request, *args, **kwargs):
        try:
            return self.create(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))


class ChoiceView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    serializer_class = ChoiceSerializer
    permission_classes = (ChoiceModelPermissions,)

    def perform_destroy(self, instance):
        instance.disable()

    def put(self, request, *args, **kwargs):
        try:
            return self.update(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

    def patch(self, request, *args, **kwargs):
        try:
            return self.partial_update(request, *args, **kwargs)
        except IntegrityError as integrity_error:
            return return_409_response(message=str(integrity_error))

    def get_queryset(self):
        return Choice.objects.all()
