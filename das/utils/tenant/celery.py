from __future__ import annotations

import logging
import random

import celery
from celery import Task, shared_task
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
    # Disable Celery's argument type checking. The fan-out passes tenant_domain
    # as an extra kwarg that __call__ consumes before it reaches run().
    typing = False

    # Max random countdown (seconds) applied to per-tenant dispatches to stagger
    # execution across workers. Set to 0 to disable. Override in task decorator
    # or subclass to control stagger per task.
    fan_out_max_countdown: int = 0

    def get_key(self, args=None, kwargs=None):
        """Generate the QueueOnce lock key, including tenant_domain when present.

        The base get_key uses inspect.signature.bind() against the task function,
        which would fail on tenant_domain since task functions don't declare it.
        We strip it before calling super(), then append it to the key so each
        tenant gets its own lock.
        """
        kwargs = dict(kwargs) if kwargs else {}
        tenant_domain = kwargs.pop("tenant_domain", None)
        key = super().get_key(args=args, kwargs=kwargs)
        if tenant_domain:
            key = f"{key}_tenant_domain-{tenant_domain}"
        return key

    def __call__(self, *args, **kwargs):
        tenant_domain = kwargs.get("tenant_domain")
        if tenant_domain:
            # Per-tenant execution. Don't pop tenant_domain from kwargs —
            # after_return needs the original kwargs to generate the matching
            # lock key for cleanup.
            run_kwargs = {k: v for k, v in kwargs.items() if k != "tenant_domain"}
            try:
                with TenantContextManager(tenant_domain):
                    logger.info("Running: %s for Tenant domain: %s", self.name, tenant_domain)
                    return self.run(*args, **run_kwargs)
            except DASTenant.DoesNotExist:
                logger.warning("Tenant with domain %s missing in local DB", tenant_domain)
            except TenantNotFoundException:
                logger.warning("Tenant with domain %s missing in TMS", tenant_domain)
            return

        tenants = get_current_cluster_domains()
        if not tenants:
            logger.warning("No tenants found in cluster!")
            return

        # Use the QueueOnce timeout as message expiry so stale per-tenant
        # messages don't pile up when the worker can't keep pace with beat.
        once_timeout = self.once.get("timeout", self.default_timeout)

        for tenant_domain in tenants:
            task_kwargs = {**kwargs, "tenant_domain": tenant_domain}
            async_opts: dict = {"expires": once_timeout}
            if self.fan_out_max_countdown:
                async_opts["countdown"] = random.randint(0, self.fan_out_max_countdown)
            # Dispatch the actual task per tenant. This goes through
            # QueueOnce.apply_async (dedup per task+tenant) and task_routes
            # matches the real task name for queue routing.
            self.apply_async(args=args, kwargs=task_kwargs, **async_opts)


@shared_task(bind=True, name=TENANT_TASK_NAME)
def by_single_tenant_task(self, task_name, args, task_kwargs):
    """Legacy helper task kept for in-flight message compatibility.

    New dispatches go directly through OverAllTenantTask.apply_async().
    This can be removed once all queues have been drained of old messages.
    """
    task = celery.current_app.tasks[task_name]
    return task(*args, **task_kwargs)
