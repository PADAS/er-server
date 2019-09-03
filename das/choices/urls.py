from django.conf.urls import url, include
from choices import views

urlpatterns = [
    url(r'^icons/download/?$', views.ChoiceIconZip.as_view(), name='icon-zip')
]