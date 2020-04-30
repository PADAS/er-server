import json
import logging
# Use python unit test here to persist results in test DB
from unittest.mock import patch

import pymet
import yaml
import urllib
from django.test import TestCase
from django.core.files import File
from osgeo import ogr
from django.core.serializers import serialize

from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.geofence import GeofenceAnalyzer, GeofenceAnalyzerConfig
from analyzers.models import SubjectAnalyzerResult
from analyzers.tasks import analyze_subject
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic, SpatialFeatureFile
from mapping.spatialfile_utils import process_spatialfile
from observations.models import (DEFAULT_ASSIGNED_RANGE, Source, Subject,
                                 SubjectGroup, SubjectSource,
                                 SubjectTrackSegmentFilter)

from .analyzer_test_utils import *
from .geofence_test_data import *
from .geofence_test_geojson import *

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
        return json.dumps(yaml.load(schema_yaml, Loader=yaml.SafeLoader))

    def setUp(self):

        data = File(open('./analyzers/fixtures/lines.geojson', 'rb'))
        feature_types_file = File(open('./analyzers/fixtures/spatial_feature_types.geojson', 'rb'))
        spatialfile = SpatialFeatureFile.objects.create(data=data, feature_types_file=feature_types_file)
        process_spatialfile(spatialfile)

        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        EventType.objects.get_or_create(
            value='geofence_break',
            category=ec,
            defaults=dict(display='Geofence Analyzer', schema=self.event_schema_json()))

    def test_geofencing_integration(self):

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(name='Jolie', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='006')
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id='elephant', speed_KmHr=7.0)

        sg = SubjectGroup.objects.create(name='geofence_subject_analyzer_group1', )
        sg.subjects.add(sub)
        sg.save()

        # Create a SpatialFeatureGroupStatic group with the 'Moukabala-Doudou'
        # geofence
        geofences = SpatialFeature.objects.filter(name__iexact='Moukalaba-Doudou')
        logger.info('Geofence count: %s' % len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(name='Gabon Geofences', )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        test_observations = [parse_recorded_at(x) for x in JOLIE_TRACK]
        test_observations = list(time_shift(test_observations))

        # Create the Geofence Analyzer Config object
        GeofenceAnalyzerConfig.objects.create(subject_group=sg, critical_geofence_group=gf_grp, search_time_hours=24.0)

        for idx in range(0, len(test_observations) - 2):
            # Store the entire list of observations.
            store_observations(test_observations[idx:idx+1], timeshift=False, source=source)
            analyze_subject(str(sub.id))

        results = SubjectAnalyzerResult.objects.filter(subject=sub)

        for result in results:
            print(f'Geofence Result: {result}')

        self.assertEqual(len(results), 1)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print(f'Event Details: {ed.data}')

    def test_geofencing_logic(self):
        """ Test functioning of the geofence algorithm logic"""

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(
            name='Olchoda', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='geofence_subject_analyzer_group2', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s', len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(name='Mara Geofences',)
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(name='Pardamat Conservancy')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(name='Geofence Containment Regions',)
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp, containment_regions=cr_grp)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len+1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2:i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        self.assertTrue(len(results) == 2)
        for result in results:
            print('Geofence Result: %s' % result)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)

    def test_geofencing_for_crooked_boundaries(self):
        sub = Subject.objects.create(
            name='dumbo', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='geofence_subject_analyzer_group2', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in DUMBO_TRACKS]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s', len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name='Crooked Geofences', )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(
            name='Pardamat Conservancy')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name='Geofence Containment Regions', )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp,
            containment_regions=cr_grp)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len+1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2:i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            print('Geofence Result: %s' % result)

        self.assertEqual(len(results), 6)


    def test_geofencing_for_a_double_hop(self):
        sub = Subject.objects.create(
            name='dumbo', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='geofence_subject_analyzer_group2', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s', len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name='Crooked Geofences', )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(
            name='Pardamat Conservancy')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name='Geofence Containment Regions', )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp,
            containment_regions=cr_grp)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len+1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2:i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            logger.info('Geofence Result: %s' % result)

        self.assertEqual(len(results), 1)

        if logger.isEnabledFor(logging.DEBUG):
            # Write results to a local file.
            fences = json.loads(
                serialize('geojson', gf_grp.features.all(),
                          geometry_field='feature_geometry', fields=('name', 'id'))
            )
            fences['features'] = fences['features'] + [self.feature_from_observation_list(test_observations)]

            fence_breaks = json.loads(
                serialize('geojson', SubjectAnalyzerResult.objects.filter(subject=sub),
                          geometry_field='geometry_collection', fields=('title', 'estimated_time'))
            )

            fences['features'] = fences['features'] + fence_breaks['features']

            with open('test_geofencing_for_a_double_hop-results.json', 'w') as fo:
                json.dump(fences, fo, indent=2)

            # Print a link to view results at geojson.io
            data = urllib.parse.quote(json.dumps(fences))
            print(f'http://geojson.io/#data=data:application/json,{data}')


    def test_illegitimate_fence_crossings(self):
        sub = Subject.objects.create(
            name='dumbo', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='geofence_subject_analyzer_group2', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in TUMBO_TRACKS]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s', len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name='Crooked Geofences', )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(
            name='Ol Donyo Farm 2')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name='Geofence Containment Regions', )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp,
            containment_regions=cr_grp)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len+1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2:i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            print('Geofence Result: %s' % result)

        self.assertEqual(len(results), 0)

    def test_zero_crossings(self):
        sub = Subject.objects.create(
            name='dumbo', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(
            name='geofence_subject_analyzer_group2', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in ZERO_CROSSINGS]
        relocs_len = len(test_observations)
        test_observations = list(generate_observations(test_observations))

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2'
        # geofence
        geofences = SpatialFeature.objects.filter(
            name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s', len(geofences))
        gf_grp = SpatialFeatureGroupStatic.objects.create(
            name='Crooked Geofences', )
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(
            name='Ol Donyo Farm 2')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(
            name='Geofence Containment Regions', )
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(
            subject_group=sg, critical_geofence_group=gf_grp,
            containment_regions=cr_grp)

        # Iterate through the observations adding another point to the
        # trajectory on each loop
        for i in range(2, relocs_len + 1):
            try:
                analyzer = GeofenceAnalyzer(config=config, subject=sub)
                analyzer.analyze(observations=test_observations[i - 2:i])
            except InsufficientDataAnalyzerException:
                break

        # There should be 2 geofence breaks from this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=sub)
        for result in results:
            print('Geofence Result: %s' % result)

        self.assertEqual(len(results), 0)
