from django.core.management.base import BaseCommand

from activity.models import Event, EventRelationship, EventRelationshipType
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "List events"

    def handle(self, *args, **options):
        EventRelationshipType.objects.get_or_create(value="contains")
        EventRelationshipType.objects.get_or_create(value="is_linked_to")

        e0 = Event.objects.get(message="BRS")

        e1 = Event.objects.get(message="WRS")

        e2 = Event.objects.get(message="hello.")

        EventRelationship.objects.add_relationship(e0, e1, "is_linked_to")

        EventRelationship.objects.add_relationship(e1, e2, "contains")
