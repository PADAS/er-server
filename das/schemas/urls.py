from django.urls import path

from schemas import views

app_name = "schemas"

urlpatterns = [
    path("users.json", views.UsersDynamicSchemaView.as_view(), name="users"),
    path("subjects.json", views.SubjectsDynamicSchemaView.as_view(), name="subjects"),
]
