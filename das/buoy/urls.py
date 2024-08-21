from django.conf.urls import re_path

from utils.constants import regex

from . import views

urlpatterns = [
    re_path(r"^gear/?$", views.GearView.as_view(), name="gear-list-view"),
    re_path(
        rf"^gear/(?P<id>{regex.UUID})/?$",
        views.SingleGearView.as_view(),
        name="gear-view",
    ),
]
