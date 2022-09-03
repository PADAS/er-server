import pytest

from django.http import HttpResponse

from das_server.middleware import (CommonMiddlewareAppendSlashWithoutRedirect,
                                   HttpSmartRedirectResponse)


class TestCommonMiddlewareAppendSlashWithoutRedirect:
    @pytest.mark.parametrize(
        "url, expected_url",
        (
            ("/api/v1.0/activity/events", "/api/v1.0/activity/events/"),
            ("/api/v1.0/activity/events/", "/api/v1.0/activity/events/"),
        ),
    )
    def test_replace_path(self, rf, url, expected_url):
        response = HttpSmartRedirectResponse(redirect_to="/")
        request = rf.get(url)
        middleware = CommonMiddlewareAppendSlashWithoutRedirect(
            self._get_response)

        middleware.process_response(request, response)

        assert request.path == expected_url

    def _get_response(self, request):
        response = HttpResponse()
        return response
