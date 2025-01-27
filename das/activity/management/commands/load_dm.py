from django.core.management.base import CommandError

from activity.management.commands.loaddata_with_tenant import Command as LoadDataCommand
from activity.models import Event, EventCategory, EventType
from choices.models import Choice, DynamicChoice
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, LoadDataCommand):
    help = """Load a data model. File should be in dumpdata format, typically a JSON file.
    Typcally this is a replacement of the current event types, event categories and choices when setting up
    a new tenant.
    This command is a subclass of loaddata_with_tenant.py, which is a subclass of Django's loaddata command.

    The dm file is created on the source site using dumpdata:
    ```
    python manage.py dumpdata activity.eventtype activity.eventcategory choices.choice choices.dynamicchoice --format json --indent 2 --natural-foreign -o /tmp/datamodel.json
    ```

    Example: python manage.py load_dm data_model.json"""

    def handle(self, *args, **options):
        """Validation and cleanup of existing event categories, event types and choices is done first,
        then we execute the loaddata command."""

        # Validate and cleanup existing event categories, event types and choices
        if Event.objects.exists():
            raise CommandError(
                "There are existing Event objects in the database. This command is meant for empty sites."
                "Please delete all Event objects before running this command."
            )

        EventType.objects.all().delete()
        EventCategory.objects.all().delete()

        Choice.objects.all().delete()
        DynamicChoice.objects.all().delete()

        # Execute loaddata command
        super().handle(*args, **options)
