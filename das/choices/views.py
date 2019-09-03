from rest_framework.views import APIView
from rest_framework.views import Response

from choices.models import Choice
from choices.serializers import ChoiceIconZipSerializer
from utils.helpers import ZipFileCompression


class ChoiceIconZip(APIView):

    def get(self, request):
        choices = Choice.objects.values('icon').exclude(
            icon__exact='').distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        if serializer.data == []:
            msg = "No icon(s) for choices found"
            return Response(msg)

        zipfile_compress = ZipFileCompression(serializer.data)
        file_paths = zipfile_compress.check_file_type()

        return zipfile_compress.zip_compress(file_paths)
