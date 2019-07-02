import logging
from analyzers.models import SubjectAnalyzerResult
from django.test import TestCase
# Use python unit test here to persist results in test DB
#from unittest import TestCase
from django.core import management
from .geofence_test_data import *
from observations.models import Subject, Source, SubjectSource, SubjectGroup, DEFAULT_ASSIGNED_RANGE
from observations.models import SubjectTrackSegmentFilter
from mapping.models import SpatialFeature, SpatialFeatureGroupStatic
from .analyzer_test_utils import *
from activity.models import Event, EventCategory, EventType
from analyzers.geofence import GeofenceAnalyzer, GeofenceAnalyzerConfig
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.tasks import analyze_subject
import json
import yaml

logger = logging.getLogger(__name__)


class TestBug4012(TestCase):
    '''
    This is a special test case that validates a fix for a missed geofence breaks in a production site.
    '''
    fixtures = [
        'bug4012/displaycategories.yaml',
        'bug4012/featuretypes.yaml',
        'bug4012/spatialfeatures.yaml',
    ]

    def setUp(self):

        ec, created = EventCategory.objects.get_or_create(
            value='analyzer_event', defaults=dict(display='Analyzer Events'))

        EventType.objects.get_or_create(
            value='geofence_break',
            category=ec,
            defaults=dict(display='Geofence Analyzer', schema=self.event_schema_json()))

    def test_geofence_bug4012(self):

        # Create models (Subject, SubjectSource and Source)
        sub = Subject.objects.create(name='Kimbizwa', subject_subtype_id='elephant')
        source = Source.objects.create(manufacturer_id='006')
        SubjectSource.objects.create(subject=sub, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        SubjectTrackSegmentFilter.objects.create(subject_subtype_id='elephant', speed_KmHr=7.0)

        sg = SubjectGroup.objects.create(name='geofence_subject_analyzer_group1', )
        sg.subjects.add(sub)
        sg.save()

        primary_fences = SpatialFeature.objects.filter(feature_type__name='Geofence_Primary')
        primary_group = SpatialFeatureGroupStatic.objects.create(name='DAS 4022 Geofences', )
        primary_group.features.add(*primary_fences)
        primary_group.save()

        warning_fences = SpatialFeature.objects.filter(feature_type__name='Geofence_Secondary')
        warning_group = SpatialFeatureGroupStatic.objects.create(name='DAS 4022 Secondary Geofences', )
        warning_group.features.add(*warning_fences)
        warning_group.save()

        test_observations = sorted([parse_recorded_at(x) for x in DAS4022_TRACKS], key=lambda x: x['recorded_at'])
        test_observations = list(time_shift(test_observations))
        #
        # # Create the Geofence Analyzer Config object
        GeofenceAnalyzerConfig.objects.create(subject_group=sg, critical_geofence_group=primary_group,
                                              warning_geofence_group=warning_group,
                                              search_time_hours=24.0)


        store_observations(test_observations, timeshift=False, source=source)
        analyze_subject(str(sub.id))

        self.assertEqual(SubjectAnalyzerResult.objects.filter(subject=sub).count(), 7)
        self.assertEqual(Event.objects.count(), 7)

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

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

