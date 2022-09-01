"""das URL Configuration

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
import oauth2_provider.views as oauth2_views

import django.contrib.staticfiles.views
from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.urls import path, re_path
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from das_server import views
from das_server.admin import dasadmin_site

admin.autodiscover()
admin.site.enable_nav_sidebar = False

schema_view = get_schema_view(
    title="EarthRanger API Documentation", renderer_classes=[JSONOpenAPIRenderer]
)

urlpatterns = [
    re_path("api/v1.0/status/?$", views.StatusView.as_view()),
    path("api/v1.0/", include("accounts.urls")),
    path("api/v1.0/", include("observations.urls")),
    path("api/v1.0/", include("mapping.urls")),
    path("api/v1.0/sensors/", include("sensors.urls")),
    path("api/v1.0/activity/", include("activity.urls")),
    path("api/v1.0/analyzers/", include("analyzers.urls")),
    path("api/v1.0/", include("rt_api.urls")),
    path(
        "api/v1.0/api-auth/", include("rest_framework.urls",
                                      namespace="rest_framework")
    ),
    path("api/v1.0/api-schema/", schema_view, name="openapi-schema"),
    path("api/v1.0/docs/interactive/", views.SwaggerTemplate.as_view()),
    path("api/v1.0/docs/", include("docs.urls")),
    path("admin/", admin.site.urls),
    path("dasadmin/", dasadmin_site.urls),
    path("accounts/", include("accounts.urls_user")),
    path("oauth2/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    re_path("oauth2/token$", oauth2_views.TokenView.as_view(), name="token"),
    path("api/v1.0/reports/", include(("reports.urls", "reports"))),
    path("api/v1.0/usercontent/", include(("usercontent.urls", "usercontent"))),
    path("api/v1.0/", include("choices.urls")),
]


# give the api a chance to override and return json
django.conf.urls.handler404 = "utils.drf.error404View"

if settings.DEV:
    urlpatterns += [
        re_path(
            r"^(?:index.html)?$",
            django.contrib.staticfiles.views.serve,
            kwargs={"path": "index.html"},
        ),
        re_path(r"^(?P<path>.*)$", django.contrib.staticfiles.views.serve),
    ]

    try:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

else:
    urlpatterns += [
        re_path(r"^$", views.index),
    ]
