import logging
from analyzers.models import SubjectAnalyzerResult, GeofenceAnalyzerConfig
#from django.test import TestCase
# Use python unit test here to persist results in test DB
from unittest import TestCase
from django.core import management
from .geofence_test_data import *
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, DEFAULT_ASSIGNED_RANGE
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic
from .analyzer_test_utils import *
from analyzers.tasks import analyze_subject
from activity.models import Event, EventCategory, EventType
from analyzers.geofence import GeofenceAnalyzer, GeofenceAnalyzerConfig
from analyzers.exceptions import InsufficientDataAnalyzerException
import json
import yaml

logger = logging.getLogger(__name__)


class TestGeofenceAnalyzer(TestCase):

    @classmethod
    def event_schema_json(cls):
        schema_yaml = '''
            schema:
              $schema: http://json-schema.org/draft-04/schema#
              definition:
              - name
              - details
              - geofence_name
              - contain_regions
              - subject_speed_kmhr
              - subject_heading
              - total_fix_count
              properties:
                name:
                  title: Name of subject
                  type: string
                details:
                  title: Details
                  type: string
                geofence_name:
                  title: Geofence Name
                  type: string
                contain_regions:
                  title: Current Region
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
              title: EventType Geofencing
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
            value='analyzer_geofence',
            category=ec,
            defaults=dict(display='Geofence Analyzer', schema=self.event_schema_json()))

    def test_geofencing(self):
        """ Test functioning of the geofence algorithm logic"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(
            name='Olchoda', subject_type='wildlife', subject_subtype='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='geofence_subject_analyzer_group', )
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

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2' geofence
        geofences = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s' % str(len(geofences)))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name='Mara Geofences',)
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(
            name='Pardamat Conservancy')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name='Geofence Containment Regions',)
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, geofences=gf_grp, containment_regions=cr_grp)

        # Iterate through the observations adding another point to the trajectory on each loop
        for i in range(2, relocs_len):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i-2:i])
            except InsufficientDataAnalyzerException:
                break

        # # Run the analyzer
        # analyze_subject(str(sub.id))

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        self.assertTrue(len(results)== 2)
        for result in results:
            print('Geofence Result: %s' % result)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)
