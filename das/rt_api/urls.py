from django.conf.urls import patterns, url, include
from rt_api.views import *


urlpatterns = (
    # samples based on data from test fixtures
    url(r'^rtmclient.html?$', RTMClient.as_view()),
    )