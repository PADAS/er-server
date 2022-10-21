import csv
import datetime

from django.core.management.base import BaseCommand
from activity.models import EventNotification


class Command(BaseCommand):

    help = 'List all event alerts sent for an ER user. This is for alerts sent based on their rules and notification methods'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str,
                            help="ER username to filter list on")
        parser.add_argument('--output', type=str,
                            help="override where to publish the list")

    def handle(self, *args, **options):
        username = options['username']
        with open(options["output"], 'w') as fh:
            writer = csv.writer(fh)
            row = ['Event Serial', 'Event Title', 'Owner', 'Notification Type', 'Sent To',
                   'Alert Sent At', 'Nearest Revision method', 'Nearest Revision At', 'Start all revisions']
            writer.writerow(row)

            for en in EventNotification.objects.filter(owner__username=username).select_related('event').order_by('-created_at'):
                event_serial = ""
                event_title = 'missing-event'
                if en.event:
                    event_title = f'{en.event.title or en.event.event_type.display}'
                    event_serial = str(en.event.serial_number)

                row = [event_serial, event_title, en.owner,
                       en.method, en.value, en.created_at]
                if en.event:
                    closest = self.find_closest_revision(
                        en.created_at, en.event.revision.all_user())
                    row.extend(
                        (closest.action, closest.revision_at.isoformat()) if closest else ('', ''))
                    for er in en.event.revision.all_user():
                        row.append(er.action)
                        row.append(er.revision_at.isoformat())
                writer.writerow(row)

    def find_closest_revision(self, alert_created_at, revisions):
        """Find the closest revision prior to when the alert was generated

        Args:
            alert_created_at ([type]): datetime the alert was generated
            revisions ([type]): list of revisions for the particular event
        """
        closest = None
        for er in revisions:
            if er.revision_at < alert_created_at:
                if closest:
                    if alert_created_at - er.revision_at < alert_created_at - closest.revision_at:
                        closest = er
                else:
                    closest = er

        return closest
