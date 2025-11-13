from django.conf.urls import re_path

from buoy import views
from utils.constants import regex

urlpatterns = [
    re_path(r"^gear/?$", views.GearsListCreateView.as_view(), name="gear-list-create-view"),
    re_path(
        rf"^gear/(?P<id>{regex.UUID})/?$",
        views.GearView.as_view(),
        name="gear-view",
    ),
]
