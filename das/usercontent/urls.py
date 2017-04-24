from django.conf.urls import url, include
from usercontent import views


urlpatterns = [
    url(r'^file_content/(?P<id>[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?4[0-9a-fA-F]{3}-?[89abAB][0-9a-fA-F]{3}-?[0-9a-fA-F]{12})/?$',
        views.FileContent.as_view(), name='file-content-view'),
]

