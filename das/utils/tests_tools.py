from typing import Any

from django.urls import resolve

API_BASE = '/api/v1.0'


def is_url_resolved(api_path: str, view: Any) -> bool:
    """Resolve a URL path and try to get their related function. """
    url_path = api_path if api_path.startswith(
        API_BASE) else f"{API_BASE}/{api_path}"
    resolver = resolve(url_path)
    return resolver.func.cls == view


class BaseTestToolMixin:
    api_path: str
    view: Any

    def test_url_resolver(self) -> None:
        """ Generic Test for view resolution"""
        assert is_url_resolved(api_path=self.api_path, view=self.view)
