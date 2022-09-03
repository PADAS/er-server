from typing import Any

import pytest

from django.urls import resolve
from django.views.generic.base import TemplateView

from rt_api import views

API_BASE = '/api/v1.0'


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "view"), (
        ("rtmclient.html/", views.RTMClient),
        ("rtmclient.html", views.RTMClient),
        ("realtime.html", TemplateView),
    )
)
def test_urls_test_cases(path: str, view: Any):
    url_path = f"{API_BASE}/{path}"
    resolver = resolve(url_path)
    assert resolver.func.view_class == view
