from django.conf.urls import url
from django.views.generic.base import TemplateView
from rt_api.views import RTMClient

app_name = 'rt_api'

urlpatterns = (
    # samples based on data from test fixtures
    url(r'^rtmclient.html?$', RTMClient.as_view()),
    url(r'^realtime.html?$', TemplateView.as_view(
        template_name='realtime.html'), name='home')
)
