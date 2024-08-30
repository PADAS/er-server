from django.conf.urls import re_path

from buoy import views
from utils.constants import regex

urlpatterns = [
    re_path(r"^/?$", views.GearsView, name="gear-list-view"),
    re_path(
        rf"^/(?P<id>{regex.UUID})/?$",
        views.GearView,
        name="gear-view",
    ),
]
