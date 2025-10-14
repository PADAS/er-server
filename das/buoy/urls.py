from django.conf.urls import re_path

from buoy import views
from utils.constants import regex

urlpatterns = [
    re_path(r"^gear/?$", views.GearsListView.as_view(), name="gear-list-view"),
    re_path(r"^gear/?$", views.GearsCreateView.as_view(), name="gear-create-view"),
    re_path(
        rf"^gear/(?P<id>{regex.UUID})/?$",
        views.GearView.as_view(),
        name="gear-view",
    ),
]
