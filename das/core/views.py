from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tasks import get_task_status


class TaskStatusView(APIView):
    def get(self, request, task_id, *args, **kwargs):
        result = get_task_status(task_id)
        return Response(status=status.HTTP_200_OK, data=result)
