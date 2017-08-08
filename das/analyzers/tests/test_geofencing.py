from analyzers.models import GeofenceAnalyzerConfig
from django.test import TestCase
from django.core import management

from .geofence_test_data import *
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, DEFAULT_ASSIGNED_RANGE
from .analyzer_test_utils import *
from analyzers.tasks import analyze_subject


class TestGeofenceAnalyzer(TestCase):

    def setUp(self):

        # Load the geojson files into the database
        management.call_command('import_ste_spatial',
                                './analyzers/fixtures/geofence_primary.geojson',
                                './analyzers/fixtures/geofence_warning.geojson',
                                './analyzers/fixtures/national_reserve.geojson',
                                '--feature-types=./analyzers/fixtures/spatial_feature_types.geojson')


    def test_geofence_integration(self):
        # """ Test the functioning of the geofence algorithm logic"""
        #
        # # Grab prepared observation list from test data.
        # test_observations = EQUATOR_CRISS_CROSS_TRACK
        #
        # # time-shift the observations to now
        # test_observations = time_shift(test_observations)
        #
        # # parse recorded_at (from string to datetime).
        # test_observations = [parse_recorded_at(x) for x in test_observations]
        #
        # # Create models (Subject, SubjectSource and Source)
        # sub = Subject.objects.create(name='Dumbo', subject_type='wildlife', subject_subtype='elephant')
        # source = Source.objects.create(manufacturer_id='dumbos-collar')
        # SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)
        #
        # sg = SubjectGroup.objects.create(name='geofence_analyzer_group', )
        # sg.subjects.add(sub)
        # sg.save()
        #
        # GeofenceAnalyzerConfig.objects.create(subject_group=sg)
        #
        # # Create observations in database, so the Analyzer will find them.
        # for item in time_shift(test_observations):
        #     recorded_at = item['recorded_at']
        #     location = Point(x=item['longitude'], y=item['latitude'])
        #     Observation.objects.create(recorded_at=recorded_at, location=location, source=source, additional={})
        #
        # # ToDo Create a SpatialFeatureGroupStatic group
        #
        # # ToDo Create a Geofence along equator
        #
        # # ToDo Create southern and northern containment regions
        #
        # # ToDO Add geofence to the SpatialFeatureGroupStatic group
        #
        # analyze_subject(str(sub.id))
        assert(True)
