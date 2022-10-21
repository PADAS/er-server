from django.conf.urls import re_path

from choices import views
from utils.constants import regex

urlpatterns = [
    re_path(r"choices/icons/download/?$",
            views.ChoiceZipIcon.as_view(), name="icon-zip"),
    re_path(r"choices/?$", views.ChoicesView.as_view(), name="choices"),
    re_path(rf"choices/(?P<id>{regex.UUID})/?$",
            views.ChoiceView.as_view(), name="choice"),
]
