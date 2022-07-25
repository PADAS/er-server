from django.urls import path

from choices import views

urlpatterns = [
    path("choices/icons/download/", views.ChoiceZipIcon.as_view(), name="icon-zip"),
    path("choices/", views.ChoicesView.as_view(), name="choices"),
    path("choices/<uuid:id>/", views.ChoiceView.as_view(), name="choice"),
]
