from django.conf.urls import url
from analyzers.views import SpatialAnalyzerListView
app_name = 'analyzers'

urlpatterns = (
    # a list of available features
    url(r'^spatial/?$', SpatialAnalyzerListView.as_view()),


)
