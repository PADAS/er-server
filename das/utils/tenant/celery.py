import logging

from celery import Task
from celery_once import QueueOnce

from core.models import DASTenant
from utils.features import features
from utils.tenant import get_tenant_settings
from utils.tenant.managers import TenantContextManager, UnsetDASTenantContextManager

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
        if features.tms.is_on():
            # TODO: update with the TMS call to get all tenants
            with UnsetDASTenantContextManager():
                tenants = list(DASTenant.objects.all())

            for tenant in tenants:
                with TenantContextManager(tenant.domain):
                    logger.info("Running: %s for Tenant domain: %s" % (self.name, tenant.domain))
                    self.run(*args, **kwargs)
        else:
            self.run(*args, **kwargs)
