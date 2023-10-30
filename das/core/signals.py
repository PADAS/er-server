import logging
from urllib.parse import urlparse

from corsheaders.signals import check_request_enabled

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import DASTenant
from das_server import pubsub
from utils.tenant.domains import add_new_tenant_domains_to_settings
from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import TenantData

logger = logging.getLogger(__name__)


def notify_tenant_is_updated(tenant_id, message_name):
    with TenantContextManager(domain=settings.SERVER_FQDN):
        pubsub.publish({"tenant_id": tenant_id}, message_name)


@receiver(post_save, sender=DASTenant)
def tenant_post_save(sender, instance, created, **kwargs):
    add_new_tenant_domains_to_settings()

    message_name = "das.tenant.new" if created else "das.tenant.update"
    logger.info(
        "saved tenant %s with domain '%s' dispatching '%s' message, created=%s",
        instance.pk,
        instance.domain,
        message_name,
        str(created),
    )
    tenant_id = str(instance.pk)
    transaction.on_commit(lambda: notify_tenant_is_updated(tenant_id, message_name))


@receiver(check_request_enabled)
def is_cors_origin_a_valid_tenant(sender, request, **kwargs):
    try:
        domain = urlparse(request.headers.get("origin")).netloc
        TenantData(domain).get_tenant_data()
        return True
    except:
        return False
