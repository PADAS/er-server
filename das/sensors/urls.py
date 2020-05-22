from django.conf.urls import url
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework.schemas import get_schema_view

from sensors import views

schema_view = get_schema_view(
    title="DAS API Documentation",
    description="Sensors API",
    urlconf="sensors.urls",
    renderer_classes=[JSONOpenAPIRenderer]
)
urlpatterns = [
    url(r'^openapi-schema/', schema_view, name='openapi-schema'),
    url(r'^(?P<sensor_type>[\w-]{3,20})/(?P<provider_key>[\w-]{3,20})/status/?$', views.SensorObservation.as_view(),
        name='sensor-observation-view'),
]
