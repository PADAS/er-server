from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from observations.models import ERRORED, PENDING, Message
from observations.tasks import handle_outbox_message
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Retry messages from the last week"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=7, help="Number of days to look back for pending messages (default: 7)"
        )

    def handle(self, *args, **options):
        days = options["days"]
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Get all messages from the last week
        pending_messages = Message.objects.filter(
            status__in=[PENDING, ERRORED], message_time__gte=since
        ).select_related("device")

        self.stdout.write(f"Found {pending_messages.count()} pending messages from the last {days} days")

        # Retry each message
        for message in pending_messages:
            try:
                # Get the user email from the sender if it's a user
                user_email = None
                if message.sender_content_type and message.sender_content_type.model == "user":
                    user_email = message.sender.email

                # Retry the message
                handle_outbox_message.apply_async(args=(str(message.id), user_email))
                self.stdout.write(self.style.SUCCESS(f"Successfully queued retry for message {message.id}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to queue retry for message {message.id}: {str(e)}"))
