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
from django.conf.urls import include, url
from django.contrib import admin
import django.contrib.staticfiles.views
from django.conf import settings
import oauth2_provider.views as oauth2_views

from das_server import views
import das_server.metrics

urlpatterns = [
    url(r'^api/v1.0/', include('accounts.urls')),
    url(r'^api/v1.0/', include('observations.urls')),
    url(r'^api/v1.0/', include('mapping.urls')),
    url(r'^api/v1.0/tms/', include('raster.urls')),
    url(r'^api/v1.0/tracking/', include('tracking.urls')),
    url(r'^api/v1.0/sensors/', include('sensors.urls')),
    url(r'^api/v1.0/activity/', include('activity.urls')),
    url(r'^api/v1.0/', include('rt_api.urls')),
    url(r'^api/v1.0/api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api/v1.0/docs/', include('rest_framework_swagger.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^accounts/', include('accounts.urls_user')),
    url(r'^oauth2/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    url(r'^oauth2/token$', oauth2_views.TokenView.as_view(), name="token"),
]


# give the api a chance to override and return json
django.conf.urls.handler404 = 'utils.drf.error404View'

if settings.DEV:
    urlpatterns += [
        url(r'^(?:index.html)?$', django.contrib.staticfiles.views.serve,
            kwargs={'path': 'index.html'}),
        url(r'^(?P<path>.*)$', django.contrib.staticfiles.views.serve),
                ]
else:
    urlpatterns += [url(r'^$', views.index),]