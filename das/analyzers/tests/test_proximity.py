from analyzers.models import SubjectAnalyzerResult, ProximityAnalyzerConfig
from django.test import TestCase
# Use python unit test here to persist results in test DB
#from unittest import TestCase
from unittest.mock import patch
from .proximity_test_data import *
from observations.models import Subject, Source, SubjectSource, SubjectGroup, DEFAULT_ASSIGNED_RANGE
from observations.models import SubjectTrackSegmentFilter
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic
from mapping.tasks import extract_features_from_files
from .analyzer_test_utils import *
from analyzers.proximity import ProximityAnalyzer
from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
import json
import yaml
import logging
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
        out_json = json.dumps(yaml.load(schema_yaml))
        print(out_json)
        return out_json

    def setUp(self):

        # Load the geojson files into the database
        with patch('mapping.utils.cleanup_files') as mock_cleanup:
            mock_cleanup.return_value = None
            data_files = ['./analyzers/fixtures/lines.geojson',
                          './analyzers/fixtures/polygons.geojson']
            feature_types_file = './analyzers/fixtures/spatial_feature_types.geojson'
            extract_features_from_files(data_files, 'ste', None, feature_types_file, name_field='', )

        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        EventType.objects.get_or_create(
            value='proximity',
            category=ec,
            defaults=dict(display='Proximity Analyzer', schema=self.event_schema_json()))

    def test_proximity_analyzer_logic(self):
        """ Test the functioning of the proximity analyzer"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(
            name='Olchoda', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='008')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='elephant', speed_KmHr=7.0)

        sg = SubjectGroup.objects.create(
            name='proximity_subject_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

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

        # Create the analyzer
        analyzer = ProximityAnalyzer(config=config, subject=sub)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len):
            try:
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
