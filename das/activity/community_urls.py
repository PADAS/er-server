from __future__ import annotations

from django.urls import include, path, re_path
from rest_framework.routers import SimpleRouter

from activity.views.community_input import CommunityInputViewSet
from activity.views.community_input_public import (
    CommunityInputEventFilesView,
    CommunityInputEventNotesView,
    CommunityInputEventSchemaView,
    CommunityInputEventsView,
    CommunityInputEventTypesViewSet,
    CommunityInputIconDownloadView,
)
from schemas.views import CommunityInputEventTypesDynamicSchemaView

router = SimpleRouter()
router.trailing_slash = "/?"
router.register(r"eventtypes", CommunityInputEventTypesViewSet, basename="community-eventtype")

_detail_action_map = {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}

_community_input_patterns = [
    path("", include(router.urls)),
    path(
        "schemas/event_types.json",
        CommunityInputEventTypesDynamicSchemaView.as_view(),
        name="community-event-types-schema",
    ),
    path("activity/events/schema/", CommunityInputEventSchemaView.as_view(), name="community-events-schema"),
    path("activity/events/", CommunityInputEventsView.as_view(), name="community-events"),
    re_path(
        r"^activity/events/eventtypes/icons/(?P<icon_id>[^/]+)/?$",
        CommunityInputIconDownloadView.as_view(),
        name="community-eventtype-icon-download",
    ),
    path(
        "activity/events/<uuid:id>/notes/",
        CommunityInputEventNotesView.as_view(),
        name="community-event-notes",
    ),
    path(
        "activity/events/<uuid:id>/files/",
        CommunityInputEventFilesView.as_view(),
        name="community-event-files",
    ),
]

urlpatterns = [
    path("", CommunityInputViewSet.as_view({"get": "list", "post": "create"}), name="v2-community-list"),
    path("<str:value>/", CommunityInputViewSet.as_view(_detail_action_map), name="v2-community-detail"),
    path("<str:community_input_value>/", include(_community_input_patterns)),
    # No-trailing-slash variant of v2-community-detail. Django's APPEND_SLASH
    # would normally redirect (301) to the slash version, but public callers
    # (e.g. SMS/QR-code link targets) may not follow redirects and need a
    # direct 200. Kept named for traceability so a future reader sees both
    # patterns; reverse("v2-community-detail") still resolves to the slash
    # form. Keep this in sync with the named pattern above.
    path(
        "<str:value>",
        CommunityInputViewSet.as_view(_detail_action_map),
        name="v2-community-detail-no-slash",
    ),
]
