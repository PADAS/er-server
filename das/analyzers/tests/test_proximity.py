import json
import logging
import os
# Use python unit test here to persist results in test DB
#from unittest import TestCase
from unittest.mock import patch

import yaml
from django.core.files import File
from django.test import TestCase

from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import FeatureProximityAnalyzerConfig, SubjectAnalyzerResult, SubjectProximityAnalyzerConfig
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer
from mapping.models import (SpatialFeature, SpatialFeatureFile,
                            SpatialFeatureGroupStatic)
from mapping.spatialfile_utils import process_spatialfile
from observations.models import (DEFAULT_ASSIGNED_RANGE, Source, Subject,
                                 SubjectGroup, SubjectSource,
                                 SubjectTrackSegmentFilter)

from .analyzer_test_utils import *
from .proximity_test_data import *

logger = logging.getLogger(__name__)

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'fixtures')

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

        data = File(open(os.path.join(FIXTURE_PATH,'lines.geojson'), 'rb'))
        feature_types_file = File(open(os.path.join(FIXTURE_PATH,'spatial_feature_types.geojson'), 'rb'))

        spatialfile = SpatialFeatureFile.objects.create(data=data, feature_types_file=feature_types_file)
        process_spatialfile(spatialfile)

        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        EventType.objects.get_or_create(
            value='proximity',
            category=ec,
            defaults=dict(display='Proximity Analyzer', schema=self.event_schema_json()))

    def test_feature_proximity_analyzer_logic(self):
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
        config = FeatureProximityAnalyzerConfig.objects.create(
            subject_group=sg, threshold_dist_meters=200, proximal_features=sf_grp)

        # Create the analyzer
        analyzer = FeatureProximityAnalyzer(config=config, subject=sub)

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

    def test_subject_proximity_analyzer_logic(self):
        """ Test the functioning of the proximity analyzer"""

        # Create models (Subject, SubjectSource and Source)

        # Analysis subject info
        sub = Subject.objects.create(
            name='Olchoda', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='008')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='elephant', speed_KmHr=7.0)
        sg = SubjectGroup.objects.create(
            name='elephants', )
        sg.subjects.add(sub)
        sg.save()

        # counter subject group info
        source2 = Source.objects.create(manufacturer_id='fatu-008')
        sub2 = Subject.objects.create(
            name='Fatu', subject_subtype_id='rhino')
        SubjectSource.objects.create(
            subject=sub2, source=source2, assigned_range=DEFAULT_ASSIGNED_RANGE)
        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='rhino', speed_KmHr=8.0)

        sg2 = SubjectGroup.objects.create(
            name='rhinos', )
        sg2.subjects.add(sub2)
        sg2.save()

        # Create test observations
        test_observations = [x for x in generate_random_positions()]
        for item in test_observations:
            recorded_at = item[0]
            location = item[1]
            models.Observation.objects.create(
                recorded_at=recorded_at, location=location, source=source, additional={})

            models.Observation.objects.create(
                recorded_at=recorded_at, location=location, source=source2, additional={})
        # Create the Proximty Analyzer Config object
        config = SubjectProximityAnalyzerConfig.objects.create(
            subject_group=sg,
            second_subject_group=sg2,
            threshold_dist_meters=200
        )
        analyzer = SubjectProximityAnalyzer(config=config, subject=sub)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        from observations.models import Observation
        analyzer.analyze(observations=Observation.objects.filter(source=source))

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
