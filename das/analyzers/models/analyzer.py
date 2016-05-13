import logging

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.db import transaction

from activity.models import Event, EventAttachment
from observations.models import Subject

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
    min_time = models.TimeField(null=True)
    max_time = models.TimeField(null=True)

    subject = models.ForeignKey(to=Subject, on_delete=models.CASCADE)

    # At least one Analyzer shouldn't report back when changing back to 'good' state
    is_two_state = True

    class Meta:
        abstract = True

    @property
    def valid_times(self):
        return (self.min_time, self.max_time)

    @property
    def name(self):
        return self.__class__.__name__

    def analyze(self, track):
        logger.info('{} analyzing {} records'.format(self.__class__.__name__, len(track)))


class AnalyzerResult(object):

    level = NOMINAL
    value = 0.0
    title = 'AnalyzerResult'
    location = None
    subject = None

    def __init__(self, analyzer, subject=None):
        self.analyzer = analyzer
        self.subject = subject

    def to_dict(self):
        """ returns a dict of attributes of this object """

        return {
            'title': self.title,
            'level': self.level,
            'value': self.value,
            'analyzer_type': self.analyzer.name,
            'analyzer_id': self.analyzer.id,
            'location': self.location and str(self.location) or None
        }

    def create_event(self):

        location = self.location and Point(self.location.x, self.location.y) or None
        message = '{0}: {1}'.format(self.title, self.subject.name)
        with transaction.atomic():
            event = Event.objects.create_event(
                event_type=self.analyzer.event_type,
                provenance=Event.ANALYZER,
                attributes=self.to_dict(),
                location=location,
                priority=analyzer_level_to_event_priority[self.level],
                message=message,
            )

            EventAttachment.objects.create_attachment(
                event=event, target=self.subject, reason=EventAttachment.TARGET)

            return event
