from typing import Optional, Type

import pytest

from django.urls import include, path
from django.views import View

from das_server.urls import urlpatterns as root_urlpatterns
from schemas.tests.test_urls import urlpatterns as test_urlpatterns


@pytest.fixture
def add_view_to_urls():
    """
    Returns a function that can add views "on the fly" to the list of urlpatterns under the "tests" namespace, using
    the specified path and name.

    Note: Make sure not to use the same route or name twice, as it will cause a collision in the urlpatterns.

    Here we are also handling cleanup so each test can start fresh ;)
    """

    root_urlpatterns.insert(
        0,
        path(
            "api/v1.0/tests/",
            include((test_urlpatterns, "tests")),
            name="tests",
        ),
    )
    original_count = len(test_urlpatterns)

    def _add_view(
        view_class: Type[View],
        route: str = "test-view/",
        name: str = "test-view",
        initkwargs: Optional[dict] = None,
    ):
        if initkwargs is None:
            initkwargs = {}
        test_urlpatterns.append(path(route, view_class.as_view(), name=name))

    # Yield the function so the test can use it
    yield _add_view

    # Cleanup: remove any url patterns we added
    while len(test_urlpatterns) > original_count:
        test_urlpatterns.pop()
    root_urlpatterns.pop(0)
