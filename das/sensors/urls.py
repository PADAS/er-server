from django.conf.urls import url
from sensors import views

urlpatterns = [
    url(r'^(?P<sensor_type>[\w-]{3,20})/(?P<provider_name>[\w-]{3,20})/status/?$', views.SensorObservation.as_view(),
        name='sensor-observation-view'),
]
