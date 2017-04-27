import logging
import uuid

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields import JSONField
from django.utils.translation import ugettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from activity.models import Event
from core.models import TimestampedModel
from observations.models import Subject, SubjectGroup, Observation
from revision.manager import Revision, RevisionMixin

logger = logging.getLogger(__name__)

# borrow levels from logging:

OK = 10
WARNING = 20
CRITICAL = 30
ERROR = 40

analyzer_level_to_event_priority = {
    OK: Event.PRI_REFERENCE,
    WARNING: Event.PRI_IMPORTANT,
    CRITICAL: Event.PRI_URGENT,
    ERROR: Event.PRI_REFERENCE,
}

class Schedule(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(null=False, max_length=50)
    value = models.CharField(null=False, max_length=50, verbose_name='Schedule represented in crontab syntax.')
    is_active = models.BooleanField(_('active'),
        default=True,
        help_text=_(
            'Designates whether this Schedule is active. '
            'Set this False instead of deleting this record.'
        ))


class SubjectAnalyzer(RevisionMixin, TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(null=False, unique=True, max_length=100,
                            verbose_name='A friendly, unique name for the analyzer.')
    notes = models.TextField(blank=True, default='')
    schedule = ArrayField(models.CharField(max_length=50), default=[],
                          verbose_name='Array of crontab schedule patterns that an analyzer can use to determine whether to run.')

    subject_group = models.ForeignKey(to=SubjectGroup, on_delete=models.CASCADE,
                                      verbose_name='This analyzer applies to subjects in this SubjectGroup.')

    revision = Revision()

    is_active = models.BooleanField(_('active'),
        default=True,
        help_text=_(
            'Designates whether this analyzer is active. '
            'Set this False instead of deleting this record.'
        ))

    class Meta:
        abstract = True

    def analyze(self, subject, last_result=None):
        raise NotImplementedError()

    def save_analyzer_result(self, last_result=None, this_result=None):
        raise NotImplementedError()

    def create_analyzer_event(self, last_result=None, this_result=None):
        raise NotImplementedError()


class SubjectAnalyzerResult(TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    analyzer_revision = models.IntegerField()
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    geometry_collection = models.GeometryCollectionField()
    estimated_time = models.DateTimeField(auto_now_add=True)
    level = models.IntegerField()
    observations = models.ManyToManyField(Observation, related_name='+')
    values = JSONField(default={}, blank=True)
    message = models.TextField(default='', blank=True)

    # TODO: Reference GeoFeature table, and FileContent (which will soon exist as models).
    # geometries = models.ForeignKey('GeoFeature', on_delete=models.PROTECT)
    # images

    # Remaining attributes are to reference the analyzer that created me.
    limits = models.Q(app_label='analyzers', model='immobilityanalyzer')
    # | models.Q(app_label='analyzers', model='geofenceanalyzer')
    subject_analyzer_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    subject_analyzer_id = models.UUIDField()
    subject_analyzer = GenericForeignKey('subject_analyzer_content_type', 'subject_analyzer_id')
    subject_analyzer_revision = models.PositiveIntegerField(default=1)


class Annotator(RevisionMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject = models.ForeignKey(to=Subject, on_delete=models.CASCADE)

    @property
    def name(self):
        return self.__class__.__name__

    def annotate(self, subject):
        logger.info('%s annotating subject: %s', self.name, subject.name)

    class Meta:
        abstract = True
