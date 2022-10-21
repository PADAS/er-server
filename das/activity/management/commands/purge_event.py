import uuid
import logging
from sys import stdin
from argparse import FileType
import fileinput

from django.core.management.base import BaseCommand
from django.db import transaction

from revision.manager import get_revision_model
import activity.models as models
from django.db import connections

REVISION_DELETIONS = [
    'delete from activity_eventrevision',
    'delete from activity_eventattachementrevision',
    'delete from activity_eventdetailsrevision',
    'delete from activity_eventfilerevision',
    'delete from activity_eventnoterevision',
    'delete from activity_eventphotorevision',
    'delete from activity_eventnotification'
]


class Command(BaseCommand):
    logger = logging.getLogger(__name__)
    help = 'Purge event(s)'

    def add_arguments(self, parser):
        parser.add_argument(
            'pks',
            nargs='?',
            type=FileType('r'),
            default=stdin,
            help='list of pk event ids to delete, by file or stdin'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='No deletion, dry run.',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        if not options['pks']:
            raise ValueError('requires list of event ids')

        with transaction.atomic():
            for pk in iter(options['pks'].readline, ''):
                self.remove_event(pk.strip())

    def remove_event(self, event_id):
        event_id = uuid.UUID(event_id)
        try:
            event = models.Event.objects.get(id=event_id)
        except models.Event.DoesNotExist:
            self.logger.info(f'Event with id {event_id} not found')
            return

        if self.dry_run:
            self.logger.info(f"Dry Run - would have removed {event_id}")
            return

        # remove supporting records
        Command.delete_qs(models.EventAttachment.objects.filter(event_id=event_id),
                          delete_revision=True)
        Command.delete_qs(models.EventDetails.objects.filter(event_id=event_id),
                          delete_revision=True)
        Command.delete_qs(models.EventFile.objects.filter(event_id=event_id),
                          delete_revision=True)
        Command.delete_qs(models.EventNote.objects.filter(event_id=event_id),
                          delete_revision=True)
        Command.delete_qs(models.EventPhoto.objects.filter(event_id=event_id),
                          delete_revision=True)
        Command.delete_qs(models.EventNotification.objects.filter(event_id=event_id),
                          delete_revision=False)
        Command.delete_qs(
            models.EventRelatedSubject.objects.filter(event_id=event_id))
        Command.delete_qs(
            models.EventRelationship.objects.filter(to_event_id=event_id))
        Command.delete_qs(
            models.EventRelationship.objects.filter(from_event_id=event_id))
        Command.delete_qs(
            models.EventsourceEvent.objects.filter(event_id=event_id))

        Command.delete_qs(models.Event.objects.filter(id=event_id),
                          delete_revision=True)

    @staticmethod
    def delete_qs(qs, delete_revision=False):
        if qs.exists():
            if delete_revision:
                for row in qs:
                    Command._raw_delete_revisions(qs.model, row.id)
            Command._raw_delete(qs)

    @staticmethod
    def _raw_delete_revisions(model, object_id):
        return Command._raw_delete(model.revision.model.objects.filter(object_id=object_id))

    @staticmethod
    def _raw_delete(qs):
        if qs.exists():
            qs._raw_delete(qs.db)
