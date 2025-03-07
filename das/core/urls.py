from django.urls import path

from core.views import TaskStatusView

urlpatterns = [
    path("taskstatus/<str:task_id>/", TaskStatusView.as_view(), name="task-status"),
]
