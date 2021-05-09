from django.db.models import Q
from django.db import IntegrityError
from django.http import Http404
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

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
                    'description': "include inactive choices"}
            ]
            operation['parameters'].extend(query_params)
        return operation


def return_409_response():
    status_msg = {
        'error_message': 'The request could not be completed due to conflict with existing data.'}
    return Response(status_msg, status=status.HTTP_409_CONFLICT)


class ChoicesView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    permission_classes = (ChoiceModelPermissions,)
    serializer_class = ChoiceSerializer
    schema = ChoicesViewSchema()

    def get_queryset(self):
        qparam = self.request.query_params

        if parse_bool(qparam.get('include_inactive')):
            queryset = Choice.objects.all()
        else:
            queryset = Choice.objects.filter_active_choices()

        queryset = queryset.filter(model=qparam.get(
            'model')) if qparam.get('model') else queryset
        queryset = queryset.filter(field=qparam.get(
            'field')) if qparam.get('field') else queryset

        return queryset.order_by('ordernum', 'display')

    def post(self, request, *args, **kwargs):
        try:
            return self.create(request, *args, **kwargs)
        except IntegrityError:
            return return_409_response()


class ChoiceView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = 'id'
    serializer_class = ChoiceSerializer
    permission_classes = (ChoiceModelPermissions,)
    queryset = Choice.objects.all()

    def perform_destroy(self, instance):
        instance.disable()

    def put(self, request, *args, **kwargs):
        try:
            return self.update(request, *args, **kwargs)
        except IntegrityError:
            return return_409_response()

    def patch(self, request, *args, **kwargs):
        try:
            return self.partial_update(request, *args, **kwargs)
        except IntegrityError:
            return return_409_response()
