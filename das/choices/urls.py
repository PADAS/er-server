from django.conf.urls import url, include
from choices import views

urlpatterns = [
    url(r'^choices/icons/download/?$', views.ChoiceZipIcon.as_view(), name='icon-zip'),
    url(r'^choices/?$', views.ChoicesView.as_view(), name='choices'),
    url(r'^choices/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$', views.ChoiceView.as_view(), name='choice')
]