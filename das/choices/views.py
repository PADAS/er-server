from rest_framework.views import APIView
from django.db.models import Q
from rest_framework.views import Response

from choices.models import Choice
from choices.serializers import ChoiceIconZipSerializer
from utils.helpers import FileCompression


class ChoiceIconZip(APIView):

    def get(self, request):
        choices = Choice.objects.values('icon').exclude(Q(
            icon__exact='') | Q(icon__exact=None)).distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        
        file_compress = FileCompression(serializer.data)
        return file_compress.zip_compress('another_name')
