import logging

import uuid

from django.contrib.gis.db import models

from activity.models import Event, EventAttachment
from observations.models import Subject
from core.models import TimestampedModel
logger = logging.getLogger(__name__)

# borrow levels from logging:

NOMINAL = 20
INFO = 20
WARNING = 30
ERROR = 40
CRITICAL = 50

analyzer_level_to_event_priority = {
    NOMINAL: Event.PRI_REFERENCE,
    WARNING: Event.PRI_IMPORTANT,
    CRITICAL: Event.PRI_URGENT
}

class Analyzer(models.Model):

    subject = models.ForeignKey(to=Subject, on_delete=models.CASCADE)

    @property
    def name(self):
        return self.__class__.__name__

    def analyze(self):
        logger.info('%s analyzing', self.name)

    def analyze(self,track):
        logger.info('%s analyzing', self.name)

    class Meta:
        abstract = True

    #def analyze(self, track):
    #    logger.info('{} analyzing {} records'.format(self.__class__.__name__, len(track)))

    # At least one Analyzer shouldn't report back when changing back to 'good' state
    #is_two_state = True


class AnalyzerResult(TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    class Meta:
        abstract = True


class Annotator(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject = models.ForeignKey(to=Subject, on_delete=models.CASCADE)

    @property
    def name(self):
        return self.__class__.__name__

    def annotate(self, subject):
        logger.info('%s annotating subject: %s', self.name, subject.name)

    class Meta:
        abstract = True
