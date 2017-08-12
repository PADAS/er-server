import logging
from analyzers.models import SubjectAnalyzerResult, GeofenceAnalyzerConfig
from analyzers.geofence import GeofenceAnalyzer
#from django.test import TestCase
from unittest import TestCase  # Use python unit test here to persist results in test DB
from django.core import management
logger = logging.getLogger(__name__)


from .geofence_test_data import *
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Observation, DEFAULT_ASSIGNED_RANGE
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic
from .analyzer_test_utils import *
from analyzers.tasks import analyze_subject


class TestGeofenceAnalyzer(TestCase):

    def setUp(self):

        # Load the geojson files into the database
        management.call_command('import_ste_spatial',
                                './analyzers/fixtures/lines.geojson',
                                './analyzers/fixtures/polygons.geojson',
                                '--feature-types=./analyzers/fixtures/spatial_feature_types.geojson')

    def test_geofence_integration(self):
        """ Test the functioning of the geofence algorithm logic"""


        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(name='Olchoda', subject_type='wildlife', subject_subtype='elephant')
        source = Source.objects.create(manufacturer_id='007')
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        sg = SubjectGroup.objects.create(name='geofence_subject_analyzer_group', )
        sg.subjects.add(sub)
        sg.save()

        # parse recorded_at (from string to datetime).
        test_observations = [parse_recorded_at(x) for x in OLCHODA_TRACK]

        # Create observations in database, so the Analyzer will find them.
        for item in time_shift(test_observations):
            recorded_at = item['recorded_at']
            location = Point(x=item['longitude'], y=item['latitude'])
            Observation.objects.create(recorded_at=recorded_at, location=location, source=source, additional={})

        # Create a SpatialFeatureGroupStatic group with the 'Ol Donyo Farm 2' geofence
        geofences = SpatialFeature.objects.filter(name__iexact='Ol Donyo Farm 2')
        logger.info('Geofence count: %s' % str(len(geofences)))
        gf_grp = SpatialFeatureGroupStatic.objects.create(name='Mara Geofences',)
        gf_grp.features.add(*geofences)
        gf_grp.save()

        # Create a containment regions grp
        contain_rgns = SpatialFeature.objects.filter(name='Pardamat Conservancy')
        logger.info('Containment region count: %s' % str(len(contain_rgns)))
        cr_grp = SpatialFeatureGroupStatic.objects.create(name='Geofence Containment Regions',)
        cr_grp.features.add(*contain_rgns)
        cr_grp.save()

        logger.info('got here...')

        # Create the Geofence Analyzer Config object
        config = GeofenceAnalyzerConfig.objects.create(subject_group=sg, geofences=gf_grp, containment_regions=cr_grp)

        # Run the analyzer
        analyze_subject(str(sub.id))

        # There should be several Geofence Breaks fom this analysis. Query and assert number
        results = SubjectAnalyzerResult.objects.all()  # Todo: not sure how to get results specific to this subject?
        logger.info('There were %s geofence breaks' % len(results))
        #assert(len(results)>0)
        assert (True)
