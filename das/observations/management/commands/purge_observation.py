import uuid
import typing
import logging
from sys import stdin
from argparse import FileType

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db import connections

from revision.manager import get_revision_model
import observations.models as models
from tracking.models import SourcePlugin
from analyzers.models import ObservationAnnotator, SubjectAnalyzerResult
from activity.models import EventRelatedSubject


class SubCommand(typing.NamedTuple):
    command: str
    model: models.TimestampedModel
    fn: str


SUB_COMMANDS = [
    SubCommand('sources', models.Source, 'remove_source'),
    SubCommand('subjects', models.Subject, 'remove_subject'),
    SubCommand('subject_groups', models.SubjectGroup, 'remove_subject_group'),
    SubCommand('source_groups', models.SourceGroup, 'remove_source_group'),
    SubCommand('source_provider', models.SourceProvider,
               'remove_source_provider'),
]


def supported_sub_commands():
    return [s.command for s in SUB_COMMANDS]


class Command(BaseCommand):
    logger = logging.getLogger(__name__)
    help = 'Purge subjects(s)'

    def add_arguments(self, parser):
        parser.add_argument(
            'pks',
            nargs='?',
            type=FileType('r'),
            default=stdin,
            help='list of pk ids to delete, by file or stdin'
        )

        parser.add_argument('sub-command', type=str,
                            help='supported commands are {0}'.format(
                                supported_sub_commands()))

        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='No deletion, dry run.',
        )

        parser.add_argument("--keep-sources",
                            help="keep these source manufacturer_ids")

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        if not options['pks']:
            raise ValueError('requires list of ids')

        self.logger.info(f'Command: {options["sub-command"]}')
        sub_command = [s for s in SUB_COMMANDS if s.command ==
                       options['sub-command']][0]

        temp = PurgeObservations(options['dry_run'], options['keep_sources'])

        with transaction.atomic():
            for pk in iter(options['pks'].readline, ''):
                pk = uuid.UUID(pk.strip())
                try:
                    obj = sub_command.model.objects.get(id=pk)
                except sub_command.model.DoesNotExist:
                    self.logger.info(
                        f'{sub_command.command} with id {pk} not found')
                    continue

                if self.dry_run:
                    self.logger.info(f"Dry Run - would have removed {pk}")
                getattr(PurgeObservations(
                    options['dry_run'], options['keep_sources']), sub_command.fn)(obj)


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


class PurgeObservations(PurgeBase):
    logger = logging.getLogger(__name__)

    def __init__(self, dry_run=False, sources_file=None):
        self.dry_run = dry_run
        self.keep_sources = []
        if sources_file:
            with open(sources_file) as fh:
                self.keep_sources = fh.readlines()

            self.keep_sources = [s.strip().lower() for s in self.keep_sources]

    def remove_subject(self, subject):
        pk = subject.id
        name = subject.name

        sources = set()

        subject_sources = models.SubjectSource.objects.filter(subject_id=pk)
        for ss in subject_sources:
            if models.SubjectSource.objects.filter(source_id=ss.source_id).exclude(subject_id=pk).count():
                self.logger.info(
                    f'Source {ss.source_id} is connected to multiple Subjects, will not delete')
            else:
                self.logger.info(
                    f'Source {ss.source_id} is connected to one subject, will delete')
                sources.add(ss.source_id)

        if not self.dry_run:
            self.delete_qs(
                models.SubjectStatus.objects.filter(subject_id=pk))
            self.delete_qs(
                subject_sources)
            self.delete_qs(ObservationAnnotator.objects.filter(subject_id=pk))
            self.delete_qs(SubjectAnalyzerResult.objects.filter(subject_id=pk))
            self.delete_qs(EventRelatedSubject.objects.filter(subject_id=pk))
            for source_id in sources:
                source = models.Source.objects.get(id=source_id)
                source_manufacturer_id = source.manufacturer_id
                if self.is_keep_source(source):
                    self.logger.info(
                        f'Source {source_manufacturer_id} on keep list, do not remove')
                    continue
                self.remove_source(source, False)
                self.logger.info(
                    f'Removed Source {source_manufacturer_id} for subject {name}')

            subject.groups.clear()
            self.delete_qs(models.Subject.objects.filter(id=pk))
            self.logger.info(f'Removed Subject {name}')
        else:
            self.logger.info(f'Dry Run, would have removed Subject {name}')

    def remove_source(self, source, include_subject_source=True):
        pk = source.id
        source_manufacturer_id = source.manufacturer_id

        if self.is_keep_source(source):
            self.logger.info(
                f'Source {source_manufacturer_id} on keep list, do not remove')
            return

        if include_subject_source and not self.dry_run:
            self.delete_qs(
                models.SubjectSource.objects.filter(source_id=pk))

        if not self.dry_run:
            source.groups.clear()
            self.delete_qs(models.Observation.objects.filter(source_id=pk))
            self.delete_qs(SourcePlugin.objects.filter(source_id=pk))
            self.delete_qs(models.Source.objects.filter(id=pk))
            self.logger.info(f'Removed Source {source_manufacturer_id}')
        else:
            self.logger.info(
                f'Dry Run, would have removed Source {source_manufacturer_id}')

    def is_keep_source(self, source):
        return source.manufacturer_id.lower() in self.keep_sources

    def remove_source_provider(self, provider):
        pk = provider.id
        name = provider.display_name
        provider_key = provider.provider_key

        self.logger.info(
            f'Removing source provider {name} and associated sources/subjects')

        subjects = models.Subject.objects.all().filter(
            subjectsource__source__provider__provider_key=provider_key)

        for subject in subjects:
            self.remove_subject(subject)

        sources = models.Source.objects.all().filter(
            provider__provider_key=provider_key)
        for source in sources:
            self.remove_source(source)

        if self.dry_run:
            self.logger.info(
                f'Dry Run, would have removed source provider {name}')
        else:
            self.delete_qs(models.SourceProvider.objects.filter(id=pk))

    def remove_source_group(self, sg):
        raise NotImplementedError()

    def remove_subject_group(self, sg):
        pk = sg.id
        name = sg.name
        if not self.dry_run:
            sg.permission_sets.clear()
            sg.subjects.clear()

            self.delete_qs(models.SubjectGroup.objects.filter(id=pk))
        self.logger.info(f'Removed SubectGroup {name}')
