import pytest

from choices import views
from utils.tests_tools import is_url_resolved

BASE_MODULE_NAME = "choices"
UUID = "63c040c4-c881-472b-87c1-c43dcc55133f"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "view"), (
        ("choices/icons/download", views.ChoiceZipIcon),
        ("choices/icons/download/", views.ChoiceZipIcon),
        ("choices", views.ChoicesView),
        ("choices/", views.ChoicesView),
        (f"choices/{UUID}", views.ChoiceView),
    )
)
def test_url_resolving(path, view):
    api_path = f"{BASE_MODULE_NAME}/{path}"
    assert is_url_resolved(api_path=api_path, view=view)
