import logging

import celery
from celery import Task, shared_task, signature
from celery_once import QueueOnce

from django.db import close_old_connections
from django.db.utils import InterfaceError, OperationalError

from core.models import DASTenant
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import get_current_cluster_domains

logger = logging.getLogger(__name__)


TENANT_TASK_NAME = "by_single_tenant_task"


class TenantTaskMixin:
    def __call__(self, *args, **kwargs):
        logger.debug("TenantTaskMixin", extra={"kwargs": kwargs})
        domain = kwargs.get("domain")
        if not domain:
            raise ValueError("domain needs to be defined via kwargs for a celery TenantTask")

        try:
            with TenantContextManager(domain):
                return super().__call__(*args, **kwargs)
        except (OperationalError, InterfaceError) as ex:
            logger.warning(
                "%s occurred while running: %s for Tenant domain: %s",
                type(ex).__name__,
                self.name,
                domain,
            )
            # default_retry_delay == 180 seconds, max_retries == 3, retry_backoff == exponential backoff, with jitter, max of ten minutes
            try:
                close_old_connections()
            except Exception:
                logger.debug("Failed to close old connections during retry for: %s", self.name)
            self.retry(exc=ex, retry_backoff=True)

    def apply(self, args=None, kwargs=None, *arg, **kw):
        args = () if args is None else args
        kwargs = kwargs or {}
        if "domain" not in kwargs:
            kwargs["domain"] = get_tenant_settings().domain

        return super().apply(args, kwargs, *arg, **kw)

    def apply_async(self, args=None, kwargs=None, *arg, **kw):
        args = () if args is None else args
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
        if "tenant_domain" in kwargs:
            tenant_domain = kwargs.pop("tenant_domain")
            try:
                with TenantContextManager(tenant_domain):
                    logger.info("Running: %s for Tenant domain: %s", self.name, tenant_domain)
                    return self.run(*args, **kwargs)
            except DASTenant.DoesNotExist:
                logger.warning("Tenant with domain %s missing in local DB", tenant_domain)
            except TenantNotFoundException:
                logger.warning("Tenant with domain %s missing in TMS", tenant_domain)
            return

        tenants = get_current_cluster_domains()
        if not tenants:
            logger.warning("No tenants found in cluster!")
            return

        for tenant_domain in tenants:
            task_kwargs = {**kwargs, "tenant_domain": tenant_domain}

            # Use helper task that's designed to accept tenant_domain
            signature(
                TENANT_TASK_NAME, args=(self.name, args), kwargs={"task_kwargs": task_kwargs}, immutable=True
            ).apply_async()


@shared_task(bind=True, name=TENANT_TASK_NAME)
def by_single_tenant_task(self, task_name, args, task_kwargs):
    """Helper task that executes the original task with tenant context"""
    task = celery.current_app.tasks[task_name]
    return task(*args, **task_kwargs)
