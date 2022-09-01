from django.urls import re_path
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from sensors import views

schema_view = get_schema_view(
    title="EarthRanger API Documentation",
    description="Sensors API",
    urlconf="sensors.urls",
    url="api/v1.0/sensors/",
    renderer_classes=[JSONOpenAPIRenderer],
)

SENSOR_TYPE: str = r"(?P<sensor_type>[\w-]{3,100})"
PROVIDER_KEY_SUFFIX: str = r"(?P<provider_key>[\w-]{3,100})/status/?$"


urlpatterns = [
    re_path(r"^openapi-schema/?$", schema_view, name="openapi-schema"),
    re_path(rf"^gsat/{PROVIDER_KEY_SUFFIX}",
            views.GsatHandlerView.as_view()),
    re_path(
        rf"^dasradioagent/{PROVIDER_KEY_SUFFIX}",
        views.RadioAgentHandlerView.as_view(),
    ),
    re_path(
        rf"^camera-trap/{PROVIDER_KEY_SUFFIX}",
        views.CameraTrapHandlerView.as_view(),
    ),
    re_path(
        rf"^vehicle-tracker-push/{PROVIDER_KEY_SUFFIX}",
        views.SkylineVehicleHandlerView.as_view(),
    ),
    re_path(
        rf"^vehicle-observation/{PROVIDER_KEY_SUFFIX}",
        views.TractVehicleHandlerView.as_view(),
    ),
    re_path(
        rf"^animal-collar-push/{PROVIDER_KEY_SUFFIX}",
        views.FollowltHandlerView.as_view(),
    ),
    re_path(
        rf"^sf-animal-tracker/{PROVIDER_KEY_SUFFIX}",
        views.SigFoxHandlerView.as_view(),
    ),
    re_path(
        rf"^gfw-alert/{PROVIDER_KEY_SUFFIX}",
        views.GFWAlertHandlerView.as_view(),
        name="gfahandler-view",
    ),
    re_path(
        rf"^sff-tracker/{PROVIDER_KEY_SUFFIX}",
        views.SigfoxFoundationHandlerView.as_view(),
        name="sigfox-v1-view",
    ),
    re_path(
        rf"^sff-tracker-v2/{PROVIDER_KEY_SUFFIX}",
        views.SigfoxV2FoundationHandlerView.as_view(),
        name="sigfox-v2-view",
    ),
    re_path(rf"^gate/{PROVIDER_KEY_SUFFIX}",
            views.GateHandlerView.as_view()),
    re_path(rf"^test/{PROVIDER_KEY_SUFFIX}",
            views.TestHandlerView.as_view()),
    re_path(
        rf"^capturs-tracker/{PROVIDER_KEY_SUFFIX}",
        views.CaptursHandlerView.as_view(),
    ),
    re_path(
        rf"^ezytrack-tracker/{PROVIDER_KEY_SUFFIX}",
        views.EzyTrackHandlerView.as_view(),
        name="ezytrack-view",
    ),
    re_path(
        rf"^inreach-tracker/{PROVIDER_KEY_SUFFIX}",
        views.InreachHandlerView.as_view(),
    ),
    re_path(
        rf"^kerlink-push/{PROVIDER_KEY_SUFFIX}",
        views.KerlinkHandlerView.as_view(),
        name="kerlink-view",
    ),
    re_path(
        rf"^ertrack/{PROVIDER_KEY_SUFFIX}",
        views.ERTrackHandlerView.as_view(),
        name="er-track-view",
    ),
    re_path(
        rf"^{SENSOR_TYPE}/{PROVIDER_KEY_SUFFIX}",
        views.GenericSensorHandlerView.as_view(),
    ),
]
