import json
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from requests import RequestException

from django.conf import settings

from core.exceptions import ConnectionTMSApiTimeoutException
from utils.tenant.exceptions import TenantNotFoundException


class BaseClient(ABC):
    @abstractmethod
    def get_tenant_data(self, domain: str):
        pass


class TestClient(BaseClient):
    def __init__(self, config):
        das_core = Path(__file__).parent
        with open(das_core / "fixtures/tenant-response.json") as tenant_response:
            self.tenant_response = json.load(tenant_response)

    def get_tenant_data(self, domain: str):
        return self.tenant_response

    def list_tenants(self):
        return [self.tenant_response]


class DjangoSettingsClient(BaseClient):
    def __init__(self, config):
        pass

    def get_tenant_data(self, domain: str):
        from utils.tenant.builder import DjangoSettingsTenantBuilder

        return DjangoSettingsTenantBuilder().build().to_dict()

    def list_tenants(self):
        tenant = self.get_tenant_data(getattr(settings, "SERVER_FQDN", None))
        return [tenant]


class HTTPClient(BaseClient):
    def __init__(self, config):
        self._host = config["HOST"]
        self._api_version = config["API_VERSION"]
        self._token = config["API_KEY"]

    def list_tenants(self):
        params = self._get_default_param()

        try:
            response = self._get("tenants", params=params)
            response.raise_for_status()
        except RequestException as request_exception:
            raise ConnectionTMSApiTimeoutException(f"Error listing tenants from the TMS API: {request_exception}")

        return response.json()

    def get_tenant_data(self, domain: str):
        params = self._get_default_param()
        params["should-refresh-cache"] = True
        try:
            response = self._get(f"tenants/{domain}", params=params)
        except RequestException as request_exception:
            raise ConnectionTMSApiTimeoutException(f"Timeout connecting to TMS API: {request_exception}")

        if response.status_code == requests.codes.ok:
            return response.json()
        raise TenantNotFoundException(
            f"TMSApi status_code={response.status_code}, message={response.reason}", domain=domain
        )

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
