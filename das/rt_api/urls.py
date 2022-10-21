from django.urls import re_path
from django.views.generic.base import TemplateView

from rt_api.views import RTMClient

app_name = 'rt_api'

urlpatterns = (
    # samples based on data from test fixtures
    re_path(r'^rtmclient.html/?$', RTMClient.as_view()),
    re_path(r'^realtime.html/?$', TemplateView.as_view(
        template_name='realtime.html'), name='home')
)
