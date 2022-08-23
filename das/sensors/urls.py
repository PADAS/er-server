from django.urls import path, register_converter
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from sensors import views

from .url_converters import ProviderKeyConverter, SensorTypeConverter

schema_view = get_schema_view(
    title="EarthRanger API Documentation",
    description="Sensors API",
    urlconf="sensors.urls",
    url="api/v1.0/sensors/",
    renderer_classes=[JSONOpenAPIRenderer],
)

register_converter(SensorTypeConverter, "sensor_type")
register_converter(ProviderKeyConverter, "provider_key")


urlpatterns = [
    path("openapi-schema/", schema_view, name="openapi-schema"),
    path("gsat/<provider_key:provider_key>/status/",
         views.GsatHandlerView.as_view()),
    path(
        "dasradioagent/<provider_key:provider_key>/status/",
        views.RadioAgentHandlerView.as_view(),
    ),
    path(
        "camera-trap/<provider_key:provider_key>/status/",
        views.CameraTrapHandlerView.as_view(),
    ),
    path(
        "vehicle-tracker-push/<provider_key:provider_key>/status/",
        views.SkylineVehicleHandlerView.as_view(),
    ),
    path(
        "vehicle-observation/<provider_key:provider_key>/status/",
        views.TractVehicleHandlerView.as_view(),
    ),
    path(
        "animal-collar-push/<provider_key:provider_key>/status/",
        views.FollowltHandlerView.as_view(),
    ),
    path(
        "sf-animal-tracker/<provider_key:provider_key>/status/",
        views.SigFoxHandlerView.as_view(),
    ),
    path(
        "gfw-alert/<provider_key:provider_key>/status/",
        views.GFWAlertHandlerView.as_view(),
        name="gfahandler-view",
    ),
    path(
        "sff-tracker/<provider_key:provider_key>/status/",
        views.SigfoxFoundationHandlerView.as_view(),
        name="sigfox-v1-view",
    ),
    path(
        "sff-tracker-v2/<provider_key:provider_key>/status/",
        views.SigfoxV2FoundationHandlerView.as_view(),
        name="sigfox-v2-view",
    ),
    path("gate/<provider_key:provider_key>/status/",
         views.GateHandlerView.as_view()),
    path("test/<provider_key:provider_key>/status/",
         views.TestHandlerView.as_view()),
    path(
        "capturs-tracker/<provider_key:provider_key>/status/",
        views.CaptursHandlerView.as_view(),
    ),
    path(
        "ezytrack-tracker/<provider_key:provider_key>/status/",
        views.EzyTrackHandlerView.as_view(),
        name="ezytrack-view",
    ),
    path(
        "inreach-tracker/<provider_key:provider_key>/status/",
        views.InreachHandlerView.as_view(),
    ),
    path(
        "kerlink-push/<provider_key:provider_key>/status/",
        views.KerlinkHandlerView.as_view(),
        name="kerlink-view",
    ),
    path(
        "ertrack/<provider_key:provider_key>/status/",
        views.ERTrackHandlerView.as_view(),
        name="er-track-view",
    ),
    path(
        "<sensor_type:sensor_type>/<provider_key:provider_key>/status/",
        views.GenericSensorHandlerView.as_view(),
    ),
]
