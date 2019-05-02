import uuid
import typing
import logging
from sys import stdin
from argparse import FileType

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.admin.models import LogEntry

from revision.manager import get_revision_model
import accounts.models as models
import oauth2_provider.models as oauth_models
from django.db import connections


class Command(BaseCommand):
    logger = logging.getLogger(__name__)
    help = 'Purge account(s)'

    def add_arguments(self, parser):
        parser.add_argument(
            'pks',
            nargs='?',
            type=FileType('r'),
            default=stdin,
            help='list of pk ids to delete, by file or stdin'
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
            raise ValueError('requires list of ids')

        with transaction.atomic():
            for pk in iter(options['pks'].readline, ''):
                pk = uuid.UUID(pk.strip())
                try:
                    obj = models.User.objects.get(id=pk)
                except models.User.DoesNotExist:
                    self.logger.info(f'User with id {pk} not found')
                    continue

                if self.dry_run:
                    self.logger.info(f"Dry Run - would have removed {pk}")
                    continue
                PurgeAccount(self.dry_run).remove_user(obj)


class PurgeBase:
    @staticmethod
    def delete_qs(qs, delete_revision=False):
        if qs.exists():
            if delete_revision:
                for row in qs:
                    PurgeBase._raw_delete_revisions(qs.model, row.id)
            PurgeBase._raw_delete(qs)

    @staticmethod
    def _raw_delete_revisions(model, object_id):
        return PurgeBase._raw_delete(model.revision.model.objects.filter(object_id=object_id))

    @staticmethod
    def _raw_delete(qs):
        if qs.exists():
            qs._raw_delete(qs.db)


class PurgeAccount(PurgeBase):
    logger = logging.getLogger(__name__)

    def __init__(self, dry_run=False):
        self.dry_run = dry_run

    def remove_user(self, user):
        username = user.username
        pk = user.id
        user.permission_sets.clear()
        self.delete_qs(
            oauth_models.get_access_token_model().objects.filter(user_id=pk))
        self.delete_qs(
            oauth_models.get_refresh_token_model().objects.filter(user_id=pk))
        self.delete_qs(LogEntry.objects.filter(user_id=pk))
        self.delete_qs(models.User.objects.filter(id=pk))
        self.logger.info(f'Deleted user {username}')
