from django.urls import path

from schemas import views

app_name = "schemas"

urlpatterns = [
    path("users.json", views.UsersDynamicSchemaView.as_view(), name="users"),
    path("subjects.json", views.SubjectsDynamicSchemaView.as_view(), name="subjects"),
    path("choices.json", views.ChoicesDynamicSchemaView.as_view(), name="choices"),
    path("spatial_features.json", views.SpatialFeaturesDynamicSchemaView.as_view(), name="spatial_features"),
    path("event_types.json", views.EventTypesDynamicSchemaView.as_view(), name="event_types"),
]
