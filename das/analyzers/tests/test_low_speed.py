from activity.models import Event, EventCategory, EventType
from unittest import TestCase
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, DEFAULT_ASSIGNED_RANGE
from analyzers.models import SubjectAnalyzerResult, LowSpeedAnalyzerConfig
from .low_speed_test_data import *
from .analyzer_test_utils import *
from analyzers.tasks import analyze_subject
import json
import yaml


class TestLowSpeedAnalyzer(TestCase):

    @classmethod
    def event_schema_json(cls):
        schema_yaml = '''
                schema:
                  $schema: http://json-schema.org/draft-04/schema#
                  definition:
                  - name
                  - details
                  - low_speed_threshold_percentile
                  - low_speed_threshold_value
                  - current_median_speed_value
                  - total_fix_count
                  properties:
                    name:
                      title: Name of subject
                      type: string
                    details:
                      title: Details
                      type: string
                    cur_median_speed:
                      title: Current Median Speed
                      type: number
                    low_speed_threshold_percentile:
                      title: Low Speed Threshold Percentile
                      type: number
                    low_speed_threshold_value:
                      title: Low Speed Threshold Value
                      type: number
                    total_fix_count:
                      title: Total Fix Count
                      type: number
                  title: EventType Geofencing
                  type: object
                '''
        return json.dumps(yaml.load(schema_yaml))

    def setUp(self):
        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        EventType.objects.get_or_create(
            value='analyzer_low_speed',
            category=ec,
            defaults=dict(display='Low Speed Analyzer', schema=self.event_schema_json()))

    def test_low_speed_analyzer_integration(self):
        """ Test the functioning of the low_speed algorithm logic"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(
            name='Olchoda', subject_type='wildlife', subject_subtype='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='low_speed_subject_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]

        # Create observations in database, so the Analyzer will find them.
        for item in time_shift(test_observations):
            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            Observation.objects.create(
                recorded_at=recorded_at, location=location, source=source, additional={})

        # Create the Low-Speed Analyzer Config object with a high value of speed to make sure we trigger the event
        LowSpeedAnalyzerConfig.objects.create(subject_group=sg, default_value=5.0)

        # Run the analyzer
        analyze_subject(str(sub.id))

        # Get the results
        results = SubjectAnalyzerResult.objects.all()
        self.assertTrue(len(results) > 0)
        for result in results:
            print('Geofence Result: %s' % result)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)