import logging

from celery import Task
from celery_once import QueueOnce

from django.conf import settings

from utils.features import features
from utils.tenant.managers import TenantContextManager

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


class TenantTask(TenantTaskMixin, Task):
    pass


class TenantQueueOnceTask(TenantTaskMixin, QueueOnce):
    pass


class OverAllTenantTask(QueueOnce):
    def __call__(self, *args, **kwargs):
        if features.tms.is_on():
            domain = settings.SERVER_FQDN
            if domain:
                with TenantContextManager(domain):
                    logger.info("Running: %s for Tenant domain: %s" % (self.name, domain))
                    self.run(*args, **kwargs)
            else:
                logger.warning("Task %s will not run because no tenants were found." % self.name)
        else:
            self.run(*args, **kwargs)
