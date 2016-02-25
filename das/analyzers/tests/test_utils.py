from django.test import TestCase

from activity.models import Event, EventAttachment
from analyzers import models, utils
from observations.models import Subject

class TestAnalyzerUtils(TestCase):

    fixtures = [
        'observations_subject.json'
    ]

    def test_get_or_create_analyzers_for_subject(self):
        """
        Ensure a subject gets a full set of default analyzers
        """

        subject = Subject.objects.get(name='Topsy')
        analyzers = list(utils.get_or_create_analyzers_for_subject(subject))

        actual = len(analyzers)
        expected = 5

        self.assertEqual(actual, expected)


    def test_latest_event_for(self):
        """
        Ensure the return of the most recent Event for a (subject|analyzer)
        """

        analyzer = models.GeofenceAnalyzer()

        subject = Subject.objects.get(name='Topsy')

        event_params = {
            'provenance': Event.ANALYZER,
            'attributes': {
                'analyzer_type': analyzer.name
            }
        }
        event1 = Event.objects.create(**event_params)
        event2 = Event.objects.create(**event_params)

        EventAttachment.objects.create(event=event1, target=subject, reason=EventAttachment.TARGET)
        EventAttachment.objects.create(event=event2, target=subject, reason=EventAttachment.TARGET)

        actual = utils.latest_event_for(subject, analyzer)
        expected = event2

        self.assertEqual(actual, expected)
