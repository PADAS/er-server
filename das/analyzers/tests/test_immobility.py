from django.contrib.gis.db import models
from django.test import TestCase

from analyzers.models import ImmobilityAnalyzerConfig, OK
from analyzers.immobility import ImmobilityAnalyzer
from observations.models import SubjectTrackSegmentFilter
from analyzers.models import SubjectAnalyzerResult
from activity.models import Event
from .immobility_test_data import *
from analyzers.tasks import analyze_subject
import analyzers.exceptions
from .analyzer_test_utils import *


class TestImmobilityAnalyzer(TestCase):

    fixtures = ['event_data_model', ]

    def test_immobility_with_moving_observations_list(self):

        test_subject = models.Subject.objects.create_subject(name='Sample')

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in ISHANGO_IMMOBILE]
        test_observations = list(generate_observations(test_observations))

        for count in range(21, 10, -1):
            try:
                config = ImmobilityAnalyzerConfig()  # default values

                ia = ImmobilityAnalyzer(config=config, subject=test_subject)
                results = ia.analyze(observations=test_observations[:count])
                result, event = results[0]
                # Break when we get to an OK result
                if result.level == OK:
                    break
            except analyzers.exceptions.InsufficientDataAnalyzerException:
                break

        # Assert we've broken from this for-loop at level=>OK and count=>17
        self.assertEqual(result.level, OK)
        # Magic number, based on Ishango test dataset
        self.assertEqual(count, 18)

    def test_integration_ishango_immobile(self):

        # Grab prepared observation list from test data.
        test_observations = ISHANGO_IMMOBILE

        # Create models (Subject, SubjectSource and Source)
        sub = models.Subject.objects.create_subject(
            name='Ishango', subject_type='wildlife', subject_subtype='elephant')
        source = models.Source.objects.create(manufacturer_id='ishango-collar')
        models.SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=models.DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype='elephant', speed_KmHr=7.0)

        sg = models.SubjectGroup.objects.create(
            name='immobility_analyzer_group',)
        sg.subjects.add(sub)
        sg.save()

        ImmobilityAnalyzerConfig.objects.create(subject_group=sg)

        # Create observations in database, so the Analyzer will find them.
        test_observations = [parse_recorded_at(x) for x in test_observations]
        store_observations(test_observations, timeshift=True, source=source)

        analyze_subject(str(sub.id))

        self.assertTrue(
            SubjectAnalyzerResult.objects.filter(subject=sub).exists())

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)

    def test_ishango_immobile(self):
        print('Analyzing: ', 'Ishango')
        test_subject = models.Subject.objects.create_subject(name='Ishango')

        # Grab prepared observation list from test data.
        test_observations = [parse_recorded_at(x) for x in ISHANGO_IMMOBILE2]
        test_observations = list(generate_observations(test_observations))

        for i in range(1, len(test_observations)):
            try:
                print('Current data-point: ', test_observations[i - 1])

                ia_config = ImmobilityAnalyzerConfig()
                ia_config.threshold_time = 18000  # 5 hours

                ia = ImmobilityAnalyzer(config=ia_config, subject=test_subject)

                results = ia.analyze(observations=test_observations[:i + 1])
                result, event = results[0]

                last_result = result

                print('Analyzer result: ', last_result)
                print('Analyzer event: ', event)
            except analyzers.exceptions.InsufficientDataAnalyzerException:
                print('Insufficient data warning')
                pass

        self.assertTrue(True)

    def test_immobility_event(self):
        """
        Test creating an Immobility Event, along with EventDetails reflecting an ImmobilityAnalyzer result.
        :return: 
        """
        from analyzers.utils import save_analyzer_event

        event_location_value = {
            'longitude': 36.5,
            'latitude': 1.5
        }

        analyzer_result_values = {
            'probability_value': .80,
            'cluster_radius': 13,
            'cluster_fix_count': 6,
            'total_fix_count': 26,
        }

        event_data = dict(
            title='Woody is immobile',
            time=pytz.utc.localize(datetime.utcnow()),
            provenance=Event.PC_ANALYZER,
            event_type='immobility',
            priority=Event.PRI_URGENT,
            location=event_location_value,
            event_details=analyzer_result_values,
        )

        e = save_analyzer_event(event_data)

        self.assertTrue(e.event_details.count() == 1)
