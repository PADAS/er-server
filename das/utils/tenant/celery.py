import logging

from celery import Task
from celery_once import QueueOnce

from utils.features import features
from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import TenantData

logger = logging.getLogger(__name__)


class TenantTask(Task):
    def __call__(self, *args, **kwargs):
        if features.tms.is_on():
            domain = kwargs.get("domain")

            if not domain:
                raise ValueError("domain needs to be defined via kwargs for a celery TenantTask")

            with TenantContextManager(domain):
                return super().__call__(*args, **kwargs)
        else:
            return super().__call__(*args, **kwargs)


class OverAllTenantTask(QueueOnce):
    def __call__(self, *args, **kwargs):
        if features.tms.is_on():
            for domain in TenantData.get_all_tenant_domains():
                with TenantContextManager(domain):
                    logger.info("Running: %s for Tenant domain: %s" % (self.name, domain))
                    self.run(*args, **kwargs)
        else:
            self.run(*args, **kwargs)
