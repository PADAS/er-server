from unittest.mock import MagicMock

import pytest
from requests import RequestException

from core.exceptions import ConnectionTMSApiTimeoutException
from core.tms import HTTPClient


@pytest.fixture
def client_mock_request(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("core.tms.requests.request", mock)
    return mock


@pytest.fixture
def mock_response():
    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.json = MagicMock()
    return response


config = {"HOST": "http://host.docker.internal:9000", "API_VERSION": "v1.0", "API_KEY": "eres-secreto-de-amor"}


class TestTMSApiClient:
    client = HTTPClient(config)

    def test_get_tenant_data(self, tenant_response, client_mock_request, mock_response):
        mock_response.json.return_value = tenant_response
        client_mock_request.return_value = mock_response

        response = self.client.get_tenant_data("chinko.pamdas.org")

        assert response == tenant_response
        client_mock_request.assert_called_once()

    def test_get_tenant_data_timeout_exception(self, tenant_response, client_mock_request, mock_response):
        mock_response.json.return_value = tenant_response
        client_mock_request.side_effect = RequestException

        with pytest.raises(ConnectionTMSApiTimeoutException):
            self.client.get_tenant_data("chinko.pamdas.org")
