import logging

from celery import Task
from celery_once import QueueOnce

from utils.features import features
from utils.tenant import get_tenant_settings
from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import get_current_cluster_domains

logger = logging.getLogger(__name__)


class TenantTaskMixin:
    def __call__(self, *args, **kwargs):
        if features.tms.is_on():
            logger.debug("TenantTaskMixin", extra={"kwargs": kwargs})
            domain = kwargs.get("domain")
            if not domain:
                raise ValueError("domain needs to be defined via kwargs for a celery TenantTask")

            with TenantContextManager(domain):
                return super().__call__(*args, **kwargs)
        else:
            return super().__call__(*args, **kwargs)

    def apply(self, args=None, kwargs=None, *arg, **kw):
        kwargs = kwargs or {}
        if "domain" not in kwargs:
            kwargs["domain"] = get_tenant_settings().domain

        return super().apply(args, kwargs, *arg, **kw)

    def apply_async(self, args=None, kwargs=None, *arg, **kw):
        kwargs = kwargs or {}
        if "domain" not in kwargs:
            kwargs["domain"] = get_tenant_settings().domain

        return super().apply_async(args, kwargs, *arg, **kw)


class TenantTask(TenantTaskMixin, Task):
    pass


class TenantQueueOnceTask(TenantTaskMixin, QueueOnce):
    pass


class OverAllTenantTask(QueueOnce):
    def __call__(self, *args, **kwargs):
        for tenant_domain in get_current_cluster_domains():
            with TenantContextManager(tenant_domain):
                logger.info("Running: %s for Tenant domain: %s", self.name, tenant_domain)
                self.run(*args, **kwargs)
