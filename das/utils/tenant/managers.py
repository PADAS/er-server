import logging
from dataclasses import asdict
from typing import Union

from django_multitenant.utils import (
    get_current_tenant,
    set_current_tenant,
    unset_current_tenant,
)

from django.core.exceptions import DisallowedHost
from django.core.handlers.wsgi import WSGIRequest
from rest_framework.request import Request

from core.models import DASTenant
from utils.tenant.domains import add_new_tenant_domains_to_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException
from utils.tenant.providers import TenantData, get_tenant_data_by_host
from utils.tenant.thread import (
    clear_tenant_settings,
    get_tenant_settings,
    set_tenant_settings,
)

logger = logging.getLogger(__name__)


class UnsetDASTenantContextManager:
    """Used to unset then reset the previous DASTenant in the current thread"""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.previous_tenant = None

    def __enter__(self):
        self.previous_tenant = get_current_tenant()
        unset_current_tenant()

    def __exit__(self, exc_type, exc_val, exc_tb):
        set_current_tenant(self.previous_tenant)


class TenantContextManager:
    def __init__(self, domain: str, *args, **kwargs):
        self.domain = domain
        self.args = args
        self.kwargs = kwargs
        self.previous_tenant_settings = None
        self.previous_tenant = None

    def __enter__(self):
        if not self.domain:
            raise ValueError("domain cannot be None or empty an string")

        self.previous_tenant = get_current_tenant()
        try:
            self.previous_tenant_settings = get_tenant_settings()
        except TenantNotFoundInLocalThreadException:
            pass

        tenant_data = TenantData(domain=self.domain).get_tenant_data()
        with UnsetDASTenantContextManager():
            try:
                tenant = DASTenant.objects.get(id=tenant_data["id"])
            except DASTenant.DoesNotExist:
                logger.debug("DASTenant with id %s does not exist", tenant_data["id"])
                raise

        set_tenant_settings(value=tenant_data)
        set_current_tenant(tenant)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.previous_tenant_settings:
            set_tenant_settings(asdict(self.previous_tenant_settings))
        else:
            clear_tenant_settings()
        set_current_tenant(self.previous_tenant)


def set_tenant_by_request(request: Union[Request, WSGIRequest]) -> None:
    """
    Single function to set both the Tenant and the DASTenant in the current thread by passing in the current request object
    """

    def get_host(request):
        try:
            return request.get_host()
        except DisallowedHost:
            add_new_tenant_domains_to_settings()

        try:
            return request.get_host()
        except DisallowedHost:
            # Host is still not in ALLOWED_HOSTS after refreshing cached
            # tenant domains. Extract the raw hostname and validate it
            # against the tenant cache / TMS before allowing it through.
            raw_host = request.META.get("HTTP_HOST", request.META.get("SERVER_NAME", ""))
            hostname = raw_host.split(":")[0]
            try:
                get_tenant_data_by_host(hostname)
                add_new_tenant_domains_to_settings(hostname=hostname)
            except Exception:
                pass

        return request.get_host()

    host_name = get_host(request)
    host_name = host_name.split(":")[0]  # remove any port number

    tenant_data = get_tenant_data_by_host(host_name)
    set_tenant_data(tenant_data)


def set_tenant(domain: str) -> None:
    """
    Single function to set both the Tenant and the DASTenant in the current thread by passing in the tenant domain name
    """
    instance = TenantData(domain=domain)
    tenant_data = instance.get_tenant_data()
    set_tenant_data(tenant_data)


def set_tenant_data(tenant_data: dict) -> None:
    """
    Single function to set both the Tenant and the DASTenant in the current thread by passing the tenant data dictionary
    """
    tenant_id = tenant_data.get("id")
    with UnsetDASTenantContextManager():
        das_tenant = DASTenant.objects.get(id=tenant_id)
    set_tenant_settings(value=tenant_data)
    set_current_tenant(tenant=das_tenant)
