from celery import Task
from celery_once import QueueOnce

from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import TenantData


class TenantTask(Task):
    def __call__(self, *args, **kwargs):
        domain = kwargs.get("domain")

        if not domain:
            raise ValueError("domain needs to be defined via kwargs for a TenantCeleryTask")

        with TenantContextManager(domain):
            return super().__call__(*args, **kwargs)


class OverAllTenantTask(QueueOnce):
    def __call__(self, *args, **kwargs):
        for domain in TenantData.get_all_tenant_domains():
            with TenantContextManager(domain):
                self.run(*args, **kwargs)
