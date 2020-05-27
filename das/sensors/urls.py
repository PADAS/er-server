from django.conf.urls import url
from django.views.generic import TemplateView
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from sensors import views

schema_view = get_schema_view(
    title="DAS API Documentation",
    description="Sensors API",
    urlconf="sensors.urls",
    url="api/v1.0/sensors",
    renderer_classes=[JSONOpenAPIRenderer]
)

url_suffix = '(?P<provider_key>[\w-]{3,20})/status/?$'

urlpatterns = [
    url(r'^openapi-schema/', schema_view, name='openapi-schema'),
    url(r'^docs/', TemplateView.as_view(
        template_name="swagger-ui.html",
        extra_context={'schema_url':'openapi-schema'})),
    url(rf'^(?P<sensor_type>[\w-]{3,20})/{url_suffix}', views.GenericSensorHandlerView.as_view()),
    url(rf'^gsat/{url_suffix}', views.GsatHandlerView.as_view()),
    url(rf'^dasradioagent/{url_suffix}', views.RadioAgentHandlerView.as_view()),
    url(rf'^camera-trap/{url_suffix}', views.CameraTrapHandlerView.as_view()),
    url(rf'^vehicle-tracker-push/{url_suffix}', views.SkylineVehicleHandlerView.as_view()),
    url(rf'^vehicle-observation/{url_suffix}', views.TractVehicleHandlerView.as_view()),
    url(rf'^animal-collar-push/{url_suffix}', views.FollowltHandlerView.as_view()),
    url(rf'^sf-animal-tracker/{url_suffix}', views.SigFoxHandlerView.as_view()),
    url(rf'^gfw-alert/{url_suffix}', views.GFWAlertHandlerView.as_view(), name='gfahandler-view'),
    url(rf'^sff-tracker/{url_suffix}', views.SigfoxFoundationHandlerView.as_view()),
    url(rf'^gate/{url_suffix}', views.GateHandlerView.as_view()),
    url(rf'^test/{url_suffix}', views.TestHandlerView.as_view()),
    url(rf'^capturs-tracker/{url_suffix}', views.CaptursHandlerView.as_view()),
    url(rf'^ezytrack-tracker/{url_suffix}', views.EzyTrackHandlerView.as_view(), name='ezytrack-view'),
    url(rf'^inreach-tracker/{url_suffix}', views.InreachHandlerView.as_view())
]
