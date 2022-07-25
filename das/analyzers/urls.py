from django.urls import path

from analyzers.views import SpatialAnalyzerListView, SubjectAnalyzerListView

app_name = "analyzers"

urlpatterns = (
    # a list of available features
    path("spatial/", SpatialAnalyzerListView.as_view()),
    path("subject/", SubjectAnalyzerListView.as_view()),
)
