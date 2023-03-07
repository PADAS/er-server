import pytest

from analyzers import views
from utils.tests_tools import is_url_resolved

BASE_MODULE_NAME = "analyzers"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "view"), (
        ("spatial", views.SpatialAnalyzerListView),
        ("spatial/", views.SpatialAnalyzerListView),
        ("subject", views.SubjectAnalyzerListView),
        ("subject/", views.SubjectAnalyzerListView),
    )
)
def test_url_resolving(path, view):
    api_path = f"{BASE_MODULE_NAME}/{path}"
    assert is_url_resolved(api_path=api_path, view=view)
