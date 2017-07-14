from django.http.response import HttpResponse
from rest_framework import generics, status, response
from usercontent.models import FileContent
from usercontent.serializers import FileContentSerializer


# class FileContentView(generics.RetrieveUpdateDestroyAPIView):
#     def get(self, request, *args, **kwargs):
#
#         if request.GET.get('data', 'false').lower() == 'true':
#             return super().get(request, *args, **kwargs)
#
#         instance = self.get_object()
#         response = HttpResponse(instance.file, content_type='application/octet-stream')
#         response['Content-Disposition'] = 'attachment; filename=%s' % instance.filename
#         return response
#
#     # permission_classes = (FileContentPermissions,)
#     serializer_class = FileContentSerializer
#
#     queryset = FileContent.objects.all()

