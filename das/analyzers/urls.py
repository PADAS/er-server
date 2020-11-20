from django.conf.urls import url
from analyzers.views import SpatialAnalyzerListView, SubjectAnalyzerListView
app_name = 'analyzers'

urlpatterns = (
    # a list of available features
    url(r'^spatial/?$', SpatialAnalyzerListView.as_view()),
    url(r'^subject/?$', SubjectAnalyzerListView.as_view()),


)
