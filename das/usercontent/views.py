from rest_framework import generics, status, response

from usercontent.serializers import FileContentSerializer

class FileContentView(generics.RetrieveUpdateDestroyAPIView):
    # permission_classes = (FileContentPermissions,)
    serializer_class = FileContentSerializer
