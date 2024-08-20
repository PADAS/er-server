from django.conf.urls import re_path

from utils.constants import regex

from . import views

urlpatterns = [
    re_path(r"^gear/?$", views.GearsView, name="gear"),
    re_path(
        rf"^gear/(?P<id>{regex.UUID})/?$",
        views.GearView,
        name="gear-view",
    ),
]
