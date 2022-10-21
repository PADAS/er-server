import pytest

from activity import views
from activity.alerts_views import AlertRuleListView
from utils.tests_tools import is_url_resolved

BASE_MODULE_NAME = "activity"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "view"), (
        ("alerts/", AlertRuleListView),
        ("events/categories/", views.EventCategoriesView),
        ("eventfilters/", views.EventFiltersView),
        ("events/eventtypes/", views.EventTypesView),
        ("eventfilters/schema/", views.EventFilterSchemaView),
        ("eventproviders/", views.EventProvidersView),
        ("patrols/", views.PatrolsView),
        ("patrols/types/", views.PatrolTypesView),
        ("patrols/segments/", views.PatrolsegmentsView),
        ("patrols/trackedby/", views.TrackedBySchema),
    )
)
def test_urls_test_cases(path, view):
    api_path = f"{BASE_MODULE_NAME}/{path}"
    assert is_url_resolved(api_path=api_path, view=view)
