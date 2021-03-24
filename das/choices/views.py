from rest_framework.views import APIView
from django.db.models import Q
from rest_framework.views import Response
from rest_framework import generics

from choices.models import Choice
from choices.serializers import ChoiceIconZipSerializer, ChoiceSerializer
from utils.helpers import FileCompression
from utils.drf import StandardResultsSetPagination
from django.http import Http404
from choices.permissions import ChoiceModelPermissions


class ChoiceZipIcon(APIView):

    def get(self, request):
        choices = Choice.objects.values('icon').exclude(Q(
            icon__exact='') | Q(icon__exact=None)).distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        if serializer.data == []:
            raise Http404()

        file_compress = FileCompression(serializer.data)
        return file_compress.zip_compress('choice_icons')


class ChoicesView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    permission_classes = (ChoiceModelPermissions,)
    serializer_class = ChoiceSerializer

    def get_queryset(self):
        queryset = Choice.objects.get_active_choices()
        qparam = self.request.query_params

        queryset = queryset.filter(model=qparam.get('model')) if qparam.get('model') else queryset
        queryset = queryset.filter(field=qparam.get('field')) if qparam.get('field') else queryset

        return queryset.order_by('ordernum', 'display')


class ChoiceView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = 'id'
    serializer_class = ChoiceSerializer
    permission_classes = (ChoiceModelPermissions,)
    queryset = Choice.objects.get_active_choices()

    def perform_destroy(self, instance):
        instance.disable()

