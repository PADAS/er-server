import json
import logging
import os
# Use python unit test here to persist results in test DB
#from unittest import TestCase
from unittest.mock import patch

import pytest
import yaml
from activity.models import Event, EventCategory, EventType
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.models import (FeatureProximityAnalyzerConfig,
                              SubjectAnalyzerResult,
                              SubjectProximityAnalyzerConfig)
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer
from django.contrib.gis.geos import LineString
from django.core.files import File
from django.test import TestCase
from django.utils import timezone
from mapping.models import (SpatialFeature, SpatialFeatureFile,
                            SpatialFeatureGroupStatic)
from mapping.spatialfile_utils import process_spatialfile
from observations.models import (DEFAULT_ASSIGNED_RANGE, Observation, Source,
                                 Subject, SubjectGroup, SubjectSource,
                                 SubjectTrackSegmentFilter)

from ..tasks import analyze_subject
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

        data = File(open(os.path.join(FIXTURE_PATH, 'lines.geojson'), 'rb'))
        feature_types_file = File(
            open(os.path.join(FIXTURE_PATH, 'spatial_feature_types.geojson'), 'rb'))

        spatialfile = SpatialFeatureFile.objects.create(
            data=data, feature_types_file=feature_types_file)
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
        analyzer.analyze(
            observations=Observation.objects.filter(source=source))

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

    def test_subject_proximity_analyzer_proximity_distance(self):
        """ Test that the subject proximity analyzer returns the proximity distance"""

        # Create models (Subject, SubjectSource and Source)
        subject_chuka = Subject.objects.create(
            name='Chuka', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='CHK001')
        SubjectSource.objects.create(
            subject=subject_chuka, source=source)
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='elephant', speed_KmHr=7.0)
        sg = SubjectGroup.objects.create(
            name='elephants', )
        sg.subjects.add(subject_chuka)
        sg.save()

        # counter subject group info
        subject_hari = Subject.objects.create(
            name='Hari', subject_subtype_id='rhino')
        source2 = Source.objects.create(manufacturer_id='HR0001')
        SubjectSource.objects.create(
            subject=subject_hari, source=source2, assigned_range=DEFAULT_ASSIGNED_RANGE)
        SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='rhino', speed_KmHr=8.0)

        sg2 = SubjectGroup.objects.create(
            name='rhinos', )
        sg2.subjects.add(subject_hari)
        sg2.save()

        recorded_at = pytz.utc.localize(datetime.now())

        coordinates = [
            [[-122.22081899642944, 47.409590070615295],
             [-122.22041130065918, 47.41009832201713]],

            [[-122.22253561019896, 47.41067917475635],
             [-122.22317934036253, 47.40943033344746]],

            [[-122.22656965255739, 47.41295895984107],
             [-122.22708463668822, 47.40986597912771]],

        ]

        for coord in coordinates:
            models.Observation.objects.create(
                recorded_at=recorded_at, location=Point(coord[0][0], coord[0][1]), source=source, additional={})
            models.Observation.objects.create(
                recorded_at=recorded_at, location=Point(coord[1][0], coord[1][1]), source=source2, additional={})

            recorded_at = recorded_at - timedelta(minutes=10)

        config = SubjectProximityAnalyzerConfig.objects.create(
            subject_group=sg,
            second_subject_group=sg2,
            threshold_dist_meters=200
        )
        analyzer = SubjectProximityAnalyzer(
            config=config, subject=subject_chuka)

        # run the analyzer function.
        analyzer.analyze()

        # There should be a bunch of proximity results fom this analysis.
        results = SubjectAnalyzerResult.objects.filter(subject=subject_chuka)

        for result in results:
            print('Proximity Result: %s' % result)
            assert result.values.get('proximity_dist_meters') > 50

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)


@pytest.mark.django_db
class TestFeatureProximityAnalyzerQuietPeriod:
    OBSERVATIONS = [
        {
            "longitude": 3.5069101510333525,
            "latitude": 9.878768920898438,
            "recorded_at": "2021-10-09T23:00:13+00:00",
        },
        {
            "longitude": 3.514449077480177,
            "latitude": 9.952239990234375,
            "recorded_at": "2021-10-09T23:30:20+00:00",
        },
        {
            "longitude": 3.5288414041434337,
            "latitude": 10.014381408691406,
            "recorded_at": "2021-10-10T00:00:24+00:00",
        },
        {
            "longitude": 3.5296177696020568,
            "latitude": 10.01674711704254,
            "recorded_at": "2021-10-10T00:00:30+00:00",
        },
    ]

    def test_proximity_quiet_period(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        feature_proximity_analyzer_config,
        dummy_cache,
        caplog,
    ):
        caplog.set_level(logging.INFO)

        subject_subtype = subject_source.subject.subject_subtype
        subject_subtype.value = "elephant"
        subject_subtype.display = "Elephant"
        subject_subtype.save()

        subtype = subject_subtype.subject_type
        subtype.value = "wildlife"
        subtype.display = "Wildlife"
        subtype.save()

        subject = subject_source.subject

        subject_group = feature_proximity_analyzer_config.subject_group
        subject_group.name = "elephants"
        subject_group.save()
        subject_group.subjects.add(subject)

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=LineString(
                Point(3.543898, 10.009698), Point(3.505531, 10.028968)
            ),
        )
        spatial_feature_group_static.features.add(spatial_feature)

        feature_proximity_analyzer_config.quiet_period = timedelta(0, 9000)
        feature_proximity_analyzer_config.proximal_features = (
            spatial_feature_group_static
        )
        feature_proximity_analyzer_config.threshold_dist_meters = 250
        feature_proximity_analyzer_config.subject_group = subject_group
        feature_proximity_analyzer_config.save()

        test_observations = [parse_recorded_at(
            point) for point in self.OBSERVATIONS]
        store_observations(
            observations=test_observations,
            timeshift=False,
            source=subject_source.source,
        )
        for minutes, observation in enumerate(Observation.objects.all(), 1):
            observation.recorded_at = timezone.now() - timedelta(
                hours=6, minutes=minutes * 15
            )
            observation.save()

        analyze_subject(subject.id)

        assert (
            f"Pausing analyzer with id={feature_proximity_analyzer_config.id}"
            in caplog.text
        )
        assert (
            f"The analyzer {feature_proximity_analyzer_config.id} is quiet for a while"
            not in caplog.text
        )
        assert Event.objects.all().count() == 1

    def test_proximity_quiet_period_check_analyzer_is_paused(
        self,
        subject_source,
        spatial_feature_type,
        spatial_feature_group_static,
        feature_proximity_analyzer_config,
        dummy_cache,
        caplog,
    ):
        caplog.set_level(logging.INFO)

        subject_subtype = subject_source.subject.subject_subtype
        subject_subtype.value = "elephant"
        subject_subtype.display = "Elephant"
        subject_subtype.save()

        subtype = subject_subtype.subject_type
        subtype.value = "wildlife"
        subtype.display = "Wildlife"
        subtype.save()

        subject = subject_source.subject

        subject_group = feature_proximity_analyzer_config.subject_group
        subject_group.name = "elephants"
        subject_group.save()
        subject_group.subjects.add(subject)

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=LineString(
                Point(3.543898, 10.009698), Point(3.505531, 10.028968)
            ),
        )
        spatial_feature_group_static.features.add(spatial_feature)

        feature_proximity_analyzer_config.quiet_period = timedelta(0, 9000)
        feature_proximity_analyzer_config.proximal_features = (
            spatial_feature_group_static
        )
        feature_proximity_analyzer_config.threshold_dist_meters = 250
        feature_proximity_analyzer_config.subject_group = subject_group
        feature_proximity_analyzer_config.save()

        test_observations = [parse_recorded_at(
            point) for point in self.OBSERVATIONS]
        store_observations(
            observations=test_observations,
            timeshift=False,
            source=subject_source.source,
        )
        for minutes, observation in enumerate(Observation.objects.all(), 1):
            observation.recorded_at = timezone.now() - timedelta(
                hours=6, minutes=minutes * 15
            )
            observation.save()

        analyze_subject(subject.id)
        analyze_subject(subject.id)

        assert (
            f"Pausing analyzer with id={feature_proximity_analyzer_config.id}"
            in caplog.text
        )
        assert (
            f"The analyzer {feature_proximity_analyzer_config.id} is quiet for a while"
            in caplog.text
        )
        assert Event.objects.all().count() == 1
