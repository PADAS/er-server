from django.conf.urls import re_path
from django.urls import path, register_converter
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from sensors import views

from .url_converters import SensorKeyConverter

schema_view = get_schema_view(
    title="EarthRanger API Documentation",
    description="Sensors API",
    urlconf="sensors.urls",
    url="api/v1.0/sensors/",
    renderer_classes=[JSONOpenAPIRenderer],
)

register_converter(SensorKeyConverter, "sensor_key")


urlpatterns = [
    path("openapi-schema/", schema_view, name="openapi-schema"),
    path("gsat/<sensor_key:provider_key>/status/",
         views.GsatHandlerView.as_view()),
    path(
        "dasradioagent/<sensor_key:provider_key>/status/",
        views.RadioAgentHandlerView.as_view(),
    ),
    path(
        "camera-trap/<sensor_key:provider_key>/status/",
        views.CameraTrapHandlerView.as_view(),
    ),
    path(
        "vehicle-tracker-push/<sensor_key:provider_key>/status/",
        views.SkylineVehicleHandlerView.as_view(),
    ),
    path(
        "vehicle-observation/<sensor_key:provider_key>/status/",
        views.TractVehicleHandlerView.as_view(),
    ),
    path(
        "animal-collar-push/<sensor_key:provider_key>/status/",
        views.FollowltHandlerView.as_view(),
    ),
    path(
        "sf-animal-tracker/<sensor_key:provider_key>/status/",
        views.SigFoxHandlerView.as_view(),
    ),
    path(
        "gfw-alert/<sensor_key:provider_key>/status/",
        views.GFWAlertHandlerView.as_view(),
        name="gfahandler-view",
    ),
    path(
        "sff-tracker/<sensor_key:provider_key>/status/",
        views.SigfoxFoundationHandlerView.as_view(),
        name="sigfox-v1-view",
    ),
    path(
        "sff-tracker-v2/<sensor_key:provider_key>/status/",
        views.SigfoxV2FoundationHandlerView.as_view(),
        name="sigfox-v2-view",
    ),
    path("gate/<sensor_key:provider_key>/status/",
         views.GateHandlerView.as_view()),
    path("test/<sensor_key:provider_key>/status/",
         views.TestHandlerView.as_view()),
    path(
        "capturs-tracker/<sensor_key:provider_key>/status/",
        views.CaptursHandlerView.as_view(),
    ),
    path(
        "ezytrack-tracker/<sensor_key:provider_key>/status/",
        views.EzyTrackHandlerView.as_view(),
        name="ezytrack-view",
    ),
    path(
        "inreach-tracker/<sensor_key:provider_key>/status/",
        views.InreachHandlerView.as_view(),
    ),
    path(
        "kerlink-push/<sensor_key:provider_key>/status/",
        views.KerlinkHandlerView.as_view(),
        name="kerlink-view",
    ),
    path(
        "ertrack/<sensor_key:provider_key>/status/",
        views.ERTrackHandlerView.as_view(),
        name="er-track-view",
    ),
    re_path(
        r"^(?P<sensor_type>[\w-]{3,100})/(?P<provider_key>[\w-]{3,100})/status/",
        views.GenericSensorHandlerView.as_view(),
    ),
]
