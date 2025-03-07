from rest_framework.response import Response
from rest_framework.views import APIView

from core.tasks import delete_object_status


class DeleteObjectStatusView(APIView):
    def get(self, request, task_id, *args, **kwargs):
        result = delete_object_status(task_id)
        return Response(result)
