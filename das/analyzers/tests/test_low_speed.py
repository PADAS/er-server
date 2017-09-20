from activity.models import Event, EventCategory, EventType
import datetime as dt
from unittest import TestCase
from django.test import TestCase
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, SubjectTrackSegmentFilter, \
    DEFAULT_ASSIGNED_RANGE
from analyzers.models import SubjectAnalyzerResult, LowSpeedAnalyzerConfig
from analyzers.models.speed_profile import SubjectSpeedProfile, SpeedDistro
from .low_speed_test_data import *
from .analyzer_test_utils import *
from analyzers.tasks import analyze_subject
import json
import yaml
import logging
logger = logging.getLogger(__name__)


class TestLowSpeedAnalyzer(TestCase):

    @classmethod
    def low_speed_event_schema_json(cls):
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
                  title: EventType Low Speed
                  type: object
                '''
        return json.dumps(yaml.load(schema_yaml))

    @classmethod
    def low_speed_all_clear_event_schema_json(cls):
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
                      title: EventType Low Speed All Clear
                      type: object
                    '''
        return json.dumps(yaml.load(schema_yaml))

    def setUp(self):
        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        'analyzer_low_speed_all_clear'
        EventType.objects.get_or_create(
            value='analyzer_low_speed',
            category=ec,
            defaults=dict(display='Low Speed Analyzer', schema=self.low_speed_event_schema_json()))

        EventType.objects.get_or_create(
            value='analyzer_low_speed_all_clear',
            category=ec,
            defaults=dict(display='Low Speed Analyzer All Clear', schema=self.low_speed_all_clear_event_schema_json()))

    def test_low_speed_analyzer(self):
        '''
        Test the functionality to update the speed percentiles for the subject 'Heritage'. Heritage was injured circa
        June 1 2012 and started moving slowly. The test dataset contains values up until June 7th 2012. Want to
        parametrize is speed percentile based on the values up until the injury, but will pick May 7 as the cutoff.
        Since we are time-shifting the observations here then need to subtract 30 days from utcnow to get the
        correct cut-off for speed distribution parametrization.
        '''

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(
            name='Heritage', subject_type='wildlife', subject_subtype='SUBTYPE_ELEPHANT')

        source = Source.objects.create(manufacturer_id='007')

        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='low_speed_subject_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        # Create a default trajectory segment filter
        SubjectTrackSegmentFilter.objects.create()

        # Decide the percentile value to use for the algorithm
        percentile = 0.25

        # Create the Low-Speed Analyzer Config object with a high value of speed to make sure we trigger the event
        LowSpeedAnalyzerConfig.objects.create(subject_group=sg, low_threshold_percentile=percentile, default_value=1.0)

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in HERITAGE_Track]

        # Create observations in database
        for item in time_shift(test_observations):
            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            Observation.objects.create(
                recorded_at=recorded_at, location=location, source=source, additional={})

        # Create a subject speed profile
        sp = SubjectSpeedProfile.objects.create(subject=sub)

        # Create a speed distribution for the speed profile
        distro = SpeedDistro.objects.create(subject_speed_profile=sp)

        # Update percentile value based on data when Heritage was moving Ok
        distro.update_percentiles([percentile], end=dt.datetime.utcnow() - dt.timedelta(days=30))

        # Test whether the value was created and its value
        test_distro = SpeedDistro.objects.first()
        self.assertTrue(test_distro is not None)
        speed_val = test_distro.percentiles[str(percentile)]
        logger.info('PercentileSpeedVal: %s' % str(speed_val))
        self.assertTrue(speed_val > 0)

        # Run the analyzer
        analyze_subject(str(sub.id))

        # Get the results
        results = SubjectAnalyzerResult.objects.all()
        self.assertTrue(len(results) > 0)
        for result in results:
            print('Low Speed Result: %s' % result)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)
