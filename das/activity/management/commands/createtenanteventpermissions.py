import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand

from activity.models import EventCategory
from activity.util import ensure_eventcategory_perms_exist
from utils.tenant import get_tenant_settings
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger("__name__")


class Command(TenantCommandMixin, BaseCommand):
    help = "Create the event category permissions for a tenant. Will create any missing ones."

    def handle(self, *args, **options):
        tenant_settings = get_tenant_settings()
        # ensure all tenant eventcategories have permissionset permissions scoped to this tenant
        for eventcategory in EventCategory.objects.all():
            ensure_eventcategory_perms_exist(eventcategory, tenant_id=tenant_settings.id)

        # next we re-load the standard event related permissions sets
        call_command(
            "loaddata_with_tenant", "migrate_event_permissionsets_codename.json", tenant_domain=tenant_settings.domain
        )
