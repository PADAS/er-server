from django.conf.urls import url
from tracking import views

urlpatterns = [
    url(r'^observations/?$', views.observation_list, ),
    url(r'^messages/?$', views.message_list, ),
]
