"""api URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import re_path
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from accounts.views import (AcceptEulaAPIView, GetActiveEulaAPIView,
                            UserProfilesView, UsersCsvView, UsersView,
                            UserView)

app_name = "accounts"

urlpatterns = [
    path("users/", UsersView.as_view()),
    path("users/csv/", UsersCsvView.as_view()),
    re_path(
        "user/(?P<id>me|[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/$",
        UserView.as_view(),
    ),
    re_path(
        r"^user/(?P<id>me|[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/profiles/$",
        UserProfilesView.as_view(),
    ),
    path("user/eula/", GetActiveEulaAPIView.as_view()),
    path("user/eula/accept", AcceptEulaAPIView.as_view()),
]

urlpatterns = format_suffix_patterns(urlpatterns)
