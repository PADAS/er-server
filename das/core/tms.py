import json
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from requests import RequestException

from django.conf import settings

from core.exceptions import ConnectionTMSApiTimeoutException
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.lookups import get_tenant_lookup_type


class BaseClient(ABC):
    @abstractmethod
    def get_tenant_data(self, lookup: str):
        pass


class TestClient(BaseClient):
    def __init__(self, config):
        das_core = Path(__file__).parent
        with open(das_core / "fixtures/tenant-response.json") as tenant_response:
            self.tenant_response = json.load(tenant_response)

    def get_tenant_data(self, lookup: str):
        lookup_type = get_tenant_lookup_type(lookup)

        if self.tenant_response[lookup_type] == lookup:
            return self.tenant_response
        raise TenantNotFoundException(f"Tenant not found in TestClient: {lookup}", domain=lookup)

    def list_tenants(self):
        return [self.tenant_response]


class DjangoSettingsClient(BaseClient):
    def __init__(self, config):
        pass

    def get_tenant_data(self, lookup: str):
        """
        Retrieve tenant data based on the provided lookup value.

        This method fetches tenant data from the TMS (Tenant Management System) using the specified lookup value.
        The lookup value can be the ID, domain, or slug_name, and is used to determine the type of lookup and fetch the
        corresponding tenant data.

        Args:
            lookup (str): The lookup value used to identify the tenant. It can be the tenant domain, tenant ID, or
            tenant slug_name.

        Returns:
            dict: A dictionary containing the tenant data if found.

        Raises:
            TenantNotFoundException: If the tenant is not found based on the lookup value.
            ConnectionTMSApiTimeoutException: If there is a timeout while connecting to the TMS API.
        """

        from utils.tenant.builder import DjangoSettingsTenantBuilder

        tenant_data = DjangoSettingsTenantBuilder().build().to_dict()

        lookup_type = get_tenant_lookup_type(lookup)
        if tenant_data[lookup_type] == lookup:
            return tenant_data
        raise TenantNotFoundException(f"Tenant not found in DjangoSettingsClient: {lookup}", domain=lookup)

    def list_tenants(self):
        tenant = self.get_tenant_data(getattr(settings, "SERVER_FQDN", None))
        return [tenant]


class DjangoSettingsClient(BaseClient):
    def __init__(self, config):
        pass

    def get_tenant_data(self, domain: str):
        from utils.tenant.builder import DjangoSettingsTenantBuilder

        return DjangoSettingsTenantBuilder().build().to_dict()


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

    def get_tenant_data(self, lookup: str):
        params = self._get_default_param()
        params["should-refresh-cache"] = True
        try:
            response = self._get(f"tenants/{lookup}", params=params)
        except RequestException as request_exception:
            raise ConnectionTMSApiTimeoutException(f"Timeout connecting to TMS API: {request_exception}")

        if response.status_code == requests.codes.ok:
            return response.json()
        raise TenantNotFoundException(
            f"TMSApi status_code={response.status_code}, message={response.reason}",
            domain=lookup,
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
