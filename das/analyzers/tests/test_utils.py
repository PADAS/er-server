from django.contrib.gis.geos import Point, LineString, MultiLineString
from django.test import TestCase

from activity.models import EventAttachment
from analyzers import models, utils
from analyzers.models.analyzer import AnalyzerResult
from mapping.models import FeatureType, LineFeature
from observations.models import Subject
from activity.tests.test_events import populate_event_types


class TestAnalyzerUtils(TestCase):

    fixtures = [
        'observations_subject.json'
    ]

    def setUp(self):
        populate_event_types()

    def test_get_or_create_analyzers_for_subject(self):
        """
        Ensure a subject gets a full set of default analyzers
        """

        subject = Subject.objects.get(name='Topsy')
        analyzers = list(utils.get_or_create_analyzers_for_subject(subject))

        actual = len(analyzers)
        expected = 5

        self.assertEqual(actual, expected)


    def test_latest_event_for_with_single_analyzer(self):
        """
        Ensure the return of the most recent Event for a (subject|analyzer)
        """

        subject = Subject.objects.get(name='Topsy')

        analyzer = models.GeofenceAnalyzer.objects.create(subject=subject)

        event1 = AnalyzerResult(analyzer, subject=subject).create_event()
        event2 = AnalyzerResult(analyzer, subject=subject).create_event()

        EventAttachment.objects.create(event=event1, target=subject, reason=EventAttachment.TARGET)
        EventAttachment.objects.create(event=event2, target=subject, reason=EventAttachment.TARGET)

        actual = utils.latest_event_for(analyzer)
        expected = event2

        self.assertEqual(actual, expected)

    def test_latest_event_for_with_multiple_analyzers(self):
        """
        Ensure the return of the most recent Event for a (subject|analyzer)
        respecting the existence of multiple instances of an analyzer type
        per subject
        """

        feature_type = FeatureType.objects.create(name='fence 1')

        # Make one GeofenceAnalyzer
        fence = MultiLineString(
            LineString((
                (-1, 1),
                (-1, -1),
            ))
        )

        polygon_feature = LineFeature.objects.create(
            presentation={},
            feature_geometry=fence,
            type=feature_type,
            name='fence1'
        )

        # Make a second GeofenceAnalyzer
        fence2 = MultiLineString(
            LineString((
                (1, 1),
                (1, -1),
            ))
        )

        polygon_feature2 = LineFeature.objects.create(
            presentation={},
            feature_geometry=fence2,
            type=feature_type,
            name='fence2'
        )

        subject = Subject.objects.get(name='Topsy')

        analyzer1 = models.GeofenceAnalyzer.objects.create(fence=polygon_feature, subject=subject)
        analyzer2 = models.GeofenceAnalyzer.objects.create(fence=polygon_feature2, subject=subject)

        # make an Event for each analyzer
        event1 = AnalyzerResult(analyzer1, subject=subject).create_event()
        event2 = AnalyzerResult(analyzer2, subject=subject).create_event()

        EventAttachment.objects.create(event=event1, target=subject, reason=EventAttachment.TARGET)
        EventAttachment.objects.create(event=event2, target=subject, reason=EventAttachment.TARGET)

        actual = utils.latest_event_for(analyzer1)
        expected = event1

        self.assertEqual(actual, expected)

        actual = utils.latest_event_for(analyzer2)
        expected = event2

        self.assertEqual(actual, expected)
