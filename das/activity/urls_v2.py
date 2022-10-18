from django.urls import include, path
from rest_framework.routers import DefaultRouter

from activity.views.types_v2 import EventTypesViewSet

router = DefaultRouter()
router.trailing_slash = "/?"
router.register(r"eventtypes", EventTypesViewSet, basename="v2-eventtype")


urlpatterns = [
    path("", include(router.urls)),
]
