from django.urls import path

from core.views import DeleteObjectStatusView

urlpatterns = [
    path("deletestatus/<str:task_id>/", DeleteObjectStatusView.as_view(), name="delete-object-status"),
]
