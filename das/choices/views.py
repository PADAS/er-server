from django.db.models import Q
from django.http import Http404
from rest_framework import generics
from rest_framework.views import APIView

from choices.models import Choice
from choices.permissions import ChoiceModelPermissions
from choices.serializers import ChoiceIconZipSerializer, ChoiceSerializer
from das_server.views import CustomSchema
from utils.drf import StandardResultsSetPagination
from utils.helpers import FileCompression
from utils.json import parse_bool


class ChoiceZipIcon(APIView):

    def get(self, request):
        choices = Choice.objects.values('icon').exclude(Q(
            icon__exact='') | Q(icon__exact=None)).distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        if serializer.data == []:
            raise Http404()

        file_compress = FileCompression(serializer.data)
        return file_compress.zip_compress('choice_icons')


class ChoicesViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [{
                'name': 'model',
                'in': 'query',
                'description': "Filter by 'model' field"},
                {
                    'name': 'field',
                    'in': 'query',
                    'description': "Filter by 'field' field"},
                {
                    'name': 'include_inactive',
                    'in': 'query',
                    'description': "include inactive choices but not disabled"}
            ]
            operation['parameters'].extend(query_params)
        return operation


class ChoicesView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    permission_classes = (ChoiceModelPermissions,)
    serializer_class = ChoiceSerializer
    schema = ChoicesViewSchema()
    queryset = Choice.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        qparam = self.request.query_params

        if parse_bool(qparam.get('include_inactive')):
            # get choices that are both active and inactive but not disabled.
            queryset = queryset.filter(delete_on__isnull=True)
        else:
            queryset = queryset.filter(delete_on__isnull=True, is_active=True)

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

