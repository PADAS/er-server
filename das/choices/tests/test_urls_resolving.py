import pytest

from choices import views
from utils.tests_tools import is_url_resolved

BASE_MODULE_NAME = "choices"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "view"), (
        ("", views.ChoicesView),
        ("icons/download/", views.ChoiceZipIcon),
    )
)
def test_urls_test_cases(path, view):
    api_path = f"{BASE_MODULE_NAME}/{path}"
    assert is_url_resolved(api_path=api_path, view=view)
