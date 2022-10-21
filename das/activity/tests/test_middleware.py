from unittest.mock import MagicMock

import pytest

from django.http import HttpResponse
from django.urls import reverse

from client_http import HTTPClient
from utils import middleware


@pytest.mark.django_db
class TestGeographicMiddleware:
    @pytest.mark.parametrize(
        "get_geo_permission_set",
        [["view_analyzer_event_geographic_distance"], []],
        indirect=True,
    )
    @pytest.mark.parametrize("location", [None])
    def test_middleware(self, rf, location, get_geo_permission_set, monkeypatch):
        mock = MagicMock(return_value=False)
        monkeypatch.setattr("utils.middleware.is_banned", mock)

        client = HTTPClient()
        client.app_user.permission_sets.add(get_geo_permission_set)
        user = client.app_user

        url = f"{reverse('events')}"
        if location:
            url += f"{url}/?location={location}"

        request = rf.get(url)
        request.user = user
        geographic_middleware = middleware.GeographicMiddleware(
            self.get_response)
        response = geographic_middleware(request)

        if (
                user.permission_sets.filter(
                    permissions__codename__icontains="geographic_distance"
                ).exists()
                and not location
        ):
            assert "warning" in response
            assert response["warning"].startswith("199")
        else:
            assert "warning" not in response

    def get_response(self, request):
        response = HttpResponse()
        return response


@pytest.mark.django_db
class TestRequestLoggingMiddleware:
    def test_call_save_location_and_block_user_temp_in_process_request(self, rf, monkeypatch):
        mock_save_location = MagicMock()
        mock_block_user_temp = MagicMock()
        monkeypatch.setattr("utils.middleware.RequestLoggingMiddleware._save_location", mock_save_location)
        monkeypatch.setattr("utils.middleware.block_user_temp", mock_block_user_temp)

        client = HTTPClient()
        user = client.app_user

        url = f"{reverse('events')}"
        request = rf.get(url)
        request.user = user

        request_logging_middleware = middleware.RequestLoggingMiddleware(
            self.get_response)

        request_logging_middleware.process_request(request)

        mock_save_location.assert_called_once()
        mock_block_user_temp.assert_called_once()

    def test_not_call_save_location_and_block_user_temp_in_process_response(self, rf, monkeypatch):
        mock_save_location = MagicMock()
        mock_block_user_temp = MagicMock()
        monkeypatch.setattr("utils.middleware.RequestLoggingMiddleware._save_location", mock_save_location)
        monkeypatch.setattr("utils.middleware.block_user_temp", mock_block_user_temp)

        client = HTTPClient()
        user = client.app_user

        url = f"{reverse('events')}"
        request = rf.get(url)
        request.user = user

        request_logging_middleware = middleware.RequestLoggingMiddleware(
            self.get_response)

        response = HttpResponse()
        request_logging_middleware.process_response(request, response)
        mock_save_location.assert_not_called()
        mock_block_user_temp.assert_not_called()

    def get_response(self, request):
        response = HttpResponse()
        return response
