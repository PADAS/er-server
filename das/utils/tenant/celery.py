import logging

from celery import Task
from celery_once import QueueOnce

from django.db.utils import OperationalError

from core.models import DASTenant
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import get_current_cluster_domains

logger = logging.getLogger(__name__)


class TenantTaskMixin:
    def __call__(self, *args, **kwargs):
        logger.debug("TenantTaskMixin", extra={"kwargs": kwargs})
        domain = kwargs.get("domain")
        if not domain:
            raise ValueError("domain needs to be defined via kwargs for a celery TenantTask")

        try:
            with TenantContextManager(domain):
                return super().__call__(*args, **kwargs)
        except OperationalError as ex:
            logger.warning("OperationalError occurred while running: %s for Tenant domain: %s", self.name, domain)
            # default_retry_delay == 180 seconds, max_retries == 3, retry_backoff == exponential backoff, with jitter, max of ten minutes
            self.retry(exc=ex, retry_backoff=True)

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
            try:
                with TenantContextManager(tenant_domain):
                    logger.info("Running: %s for Tenant domain: %s", self.name, tenant_domain)
                    self.run(*args, **kwargs)
            except DASTenant.DoesNotExist:
                logger.warning(
                    "Tenant with domain %s found in current cluster domain list does not exist in this server's tenant db",
                    tenant_domain,
                )
            except TenantNotFoundException:
                logger.warning(
                    "Tenant with domain %s found in current cluster domain list does not exist in TMS", tenant_domain
                )
