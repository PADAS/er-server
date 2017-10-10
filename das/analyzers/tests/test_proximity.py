import logging
from analyzers.models import SubjectAnalyzerResult, ProximityAnalyzerConfig
#from django.test import TestCase
# Use python unit test here to persist results in test DB
from unittest import TestCase
from django.core import management
from .proximity_test_data import *
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, DEFAULT_ASSIGNED_RANGE
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic
from .analyzer_test_utils import *
from analyzers.proximity import ProximityAnalyzer
from analyzers.tasks import analyze_subject
from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
import json
import yaml

logger = logging.getLogger(__name__)


class TestProximityAnalyzer(TestCase):

    @classmethod
    def event_schema_json(cls):
        schema_yaml = '''
            schema:
              $schema: http://json-schema.org/draft-04/schema#
              definition:
              - name
              - details
              - spatial_feature_name
              - subject_speed_kmhr
              - subject_heading
              - total_fix_count
              - proximity_dist_meters
              properties:
                name:
                  title: Name of subject
                  type: string
                details:
                  title: Details
                  type: string
                spatial_feature_name:
                  title: Spatial Feature Name
                  type: string
                subject_speed_kmhr:
                  title: Subject Speed
                  type: number
                subject_heading:
                  title: Subject Heading
                  type: number
                total_fix_count:
                  title: Total Fix Count
                  type: number
                proximity_dist_meters:
                  title: Proximity Distance Meters
                  type: number
              title: EventType Proximity
              type: object
            '''
        return json.dumps(yaml.load(schema_yaml))

    def setUp(self):

        # Load the geojson files into the database
        management.call_command('import_ste_spatial',
                                './analyzers/fixtures/lines.geojson',
                                './analyzers/fixtures/polygons.geojson',
                                '--feature-types=./analyzers/fixtures/spatial_feature_types.geojson')

        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        EventType.objects.get_or_create(
            value='analyzer_proximity',
            category=ec,
            defaults=dict(display='Proximity Analyzer', schema=self.event_schema_json()))

    def test_proximity_integration(self):
        """ Test the functioning of the proximity analyzer"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(
            name='Olchoda', subject_type='wildlife', subject_subtype='elephant')
        source = Source.objects.create(manufacturer_id='008')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='proximity_subject_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # # Create observations in database, so the Analyzer will find them.
        # for item in time_shift(test_observations):
        #     recorded_at = item['recorded_at']
        #     location = Point(x=item['longitude'], y=item['latitude'])
        #     Observation.objects.create(
        #         recorded_at=recorded_at, location=location, source=source, additional={})

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        sfs = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Proximity features count: %s' % str(len(sfs)))
        sf_grp = SpatialFeatureGroupStatic.objects.create(
            name='Mara Geofences (for proximity test)', )
        sf_grp.features.add(*sfs)
        sf_grp.save()

        # Create the Proximty Analyzer Config object
        config = ProximityAnalyzerConfig.objects.create(
            subject_group=sg, threshold_dist_meters=200, proximal_features=sf_grp)

        # Run the analyzer
        #analyze_subject(str(sub.id))

        # Iterate through the observations adding another point to the trajectory on each loop
        for i in range(2, relocs_len):
            try:
                analyzer = ProximityAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2:i])
            except InsufficientDataAnalyzerException:
                break

        # There should be a bunch of proximity results fom this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        self.assertTrue(len(results) > 0)
        for result in results:
            print('Proximity Result: %s' % result)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)
