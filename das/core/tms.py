from abc import ABC, abstractmethod

import requests
from requests import RequestException

from core.exceptions import ConnectionTMSApiTimeoutException


class BaseClient(ABC):
    @abstractmethod
    def get_tenant_data(self, domain: str):
        pass


class HTTPClient(BaseClient):
    def __init__(self, config):
        self._host = config["HOST"]
        self._api_version = config["API_VERSION"]
        self._token = config["API_KEY"]

    def get_tenant_data(self, domain: str):
        params = self._get_default_param()
        try:
            response = self._get(f"tenants/{domain}", params=params)
        except RequestException as request_exception:
            raise ConnectionTMSApiTimeoutException(f"Timeout connecting to TMS API {request_exception}")

        if response.status_code == requests.codes.ok:
            return response.json()

    def _get(self, *args, **kwargs):
        return self._make_request("get", *args, **kwargs)

    def _make_request(self, method, endpoint, **kwargs):
        url = self._get_url(endpoint)
        headers = self._get_headers()

        return requests.request(method, url, headers=headers, **kwargs)

    def _get_url(self, endpoint):
        return f"{self._host}/{self._api_version}/{endpoint}"

    def _get_headers(self):
        return {"Content-Type": "application/json"}

    def _get_default_param(self):
        return {"key": self._token}
