import logging

from django.apps import apps

from das_server import celery
from tracking.models import (
    FirmsPlugin,
    InreachKMLPlugin,
    InreachPlugin,
    SirtrackPlugin,
    SourcePlugin,
    SpiderTracksPlugin,
    runnable_plugins,
)
from tracking.models.plugin_base import (
    DasPluginConfigurationError,
    DasPluginFetchError,
    DasPluginSourceRetryError,
    TrackingPlugin,
)
from utils.features import features
from utils.tenant import get_tenant_settings
from utils.tenant.celery import OverAllTenantTask, TenantQueueOnceTask

logger = logging.getLogger(__name__)

EXPIRE_SUBTASKS = 300


@celery.app.task(base=OverAllTenantTask, bind=True, once={"graceful": True})
def run_plugins(self):
    for plugin_class in runnable_plugins:
        if issubclass(plugin_class, (TrackingPlugin,)):
            run_plugin_class.apply_async(
                kwargs=dict(plugin_class=plugin_class.__name__, domain=get_tenant_settings().domain)
            )
        else:
            logger.error(
                "Coding error. %s.%s is not runnable as a TrackingPlugin.",
                plugin_class.__module__,
                plugin_class.__name__,
            )


@celery.app.task(
    base=TenantQueueOnceTask,
    bind=True,
    once={
        "graceful": True,
    },
)
def run_plugin_class(self, plugin_class, domain=None, **kwargs):
    """Fetch all instances of plugin_class and execute."""
    if isinstance(plugin_class, str):
        plugin_class = apps.get_model("tracking", plugin_class)

    # Use passed domain or fall back to tenant settings
    effective_domain = domain or get_tenant_settings().domain

    for plugin in plugin_class.objects.all():
        if plugin.run_source_plugins:
            if plugin.status == TrackingPlugin.STATUS_ENABLED:
                for sp in plugin.source_plugins.filter(status=TrackingPlugin.STATUS_ENABLED):
                    if sp.should_run():
                        run_source_plugin.apply_async(kwargs=dict(source_plugin_id=str(sp.id), domain=effective_domain))
        else:
            plugin.execute()


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def schedule_firms_plugins():
    """
    This task is intended to run as a scheduled job.
    It delegates work to 'run_firms_plugin' which, when run using apply_async, will reject redundant/concurrent tasks.
    """
    plugins = FirmsPlugin.objects.filter(status=FirmsPlugin.STATUS_ENABLED).values("id")
    kwargs = {"domain": get_tenant_settings().domain} if features.tms.is_on() else {}
    for plugin in plugins:
        plugin_id = str(plugin["id"])
        run_firms_plugin.apply_async(args=(plugin_id,), kwargs=kwargs)


@celery.app.task(
    base=TenantQueueOnceTask,
    once={
        "graceful": True,
    },
)
def run_firms_plugin(id: str, **kwargs):
    """Run for an individual FIRMS plugin."""
    try:
        plugin = FirmsPlugin.objects.get(id=id, status=FirmsPlugin.STATUS_ENABLED)
        plugin.execute()
    except DasPluginConfigurationError as dex:
        logger.warning("FirmsPlugin %s, configuration error: %s", id, dex)
    except FirmsPlugin.DoesNotExist:
        logger.warning("Failed to find FirmsPlugin for id:%s", id)


def run_spidertracks_plugins():
    for plugin in SpiderTracksPlugin.objects.filter(status=SpiderTracksPlugin.STATUS_ENABLED):
        plugin.execute()


def run_sirtrack_plugins():
    for plugin in SirtrackPlugin.objects.filter(status=SirtrackPlugin.STATUS_ENABLED):
        plugin.execute()


@celery.app.task(
    bind=True,
    base=TenantQueueOnceTask,
    once={
        "graceful": True,
    },
    max_retries=2,
)
def run_source_plugin(self, source_plugin_id, **kwargs):
    sp = SourcePlugin.objects.get(id=source_plugin_id)

    logger.debug("Running plugin {} for source {}".format(sp, sp.source))
    try:
        result = sp.execute()
    except DasPluginFetchError as ex:
        logger.warning("Failed to fetch observations for source plugin %s. Error %s", sp, ex)
    except DasPluginConfigurationError as dex:
        logger.warning("Plugin %s, configuration error: %s", sp, dex)
    except DasPluginSourceRetryError as ex:
        logger.debug("Retry plugin {} for source {} after {}".format(sp, sp.source, ex.retry_seconds))
        self.retry(countdown=ex.retry_seconds)
    else:
        logger.debug(
            "Finished running plugin {} for source {} with result.count={}".format(sp, sp.source, result.count)
        )


def run_inreach_plugins():
    """Whether to run directly. If False, then queue tasks."""
    for plugin in InreachPlugin.objects.filter(status=InreachPlugin.STATUS_ENABLED):
        plugin.execute()


def run_inreachkml_plugins():
    """Whether to run directly. If False, then queue tasks."""
    for plugin in InreachKMLPlugin.objects.filter(status=InreachKMLPlugin.STATUS_ENABLED):
        plugin.execute()
