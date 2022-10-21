from django.test import TestCase

from activity.models import Event
from analyzers.models import EnvironmentalSubjectAnalyzerConfig
from analyzers.tasks import analyze_subject
from analyzers.tests.analyzer_test_utils import generate_random_positions
from observations import models


class TestEnvironmentAnalyzer(TestCase):

    fixtures = ['event_data_model', ]

    def setUp(self):

        # ec, created = activity.models.EventCategory.objects.get_or_create(
        #      value='analyzer_event', defaults=dict(display='Analyzer Events'))
        #
        # activity.models.EventType.objects.get_or_create(value='environmental_value', category=ec,
        #                                                 defaults=dict(
        #                                                     display='Environmental Value',
        #                                                     is_collection=False, ))
        #
        # activity.models.EventType.objects.get_or_create(value='environmental_all_clear', category=ec,
        #                                                 defaults=dict(
        #                                                     display='Environmental All Clear',
        # is_collection=False, ))
        pass

    def test_environmental_analyzer(self):
        # Create models (Subject, SubjectSource and Source)
        sub = models.Subject.objects.create_subject(
            name='RandomWalkElephant', subject_subtype_id='elephant')

        source = models.Source.objects.create(manufacturer_id='random-collar')

        models.SubjectSource.objects.create(
            subject=sub, source=source, assigned_range=models.DEFAULT_ASSIGNED_RANGE)

        # Create a SubjectTrackSegmentFilter
        models.SubjectTrackSegmentFilter.objects.create(
            subject_subtype_id='elephant', speed_KmHr=7.0)

        sg = models.SubjectGroup.objects.create(
            name='environmental_analyzer_group',)
        sg.subjects.add(sub)
        sg.save()

        EnvironmentalSubjectAnalyzerConfig.objects.create(subject_group=sg,
                                                          search_time_hours=5.0,
                                                          threshold_value=10.0,  # use a low elevation
                                                          scale_meters=500.0,
                                                          GEE_img_name='USGS/SRTMGL1_003',
                                                          GEE_img_band_name='elevation',
                                                          short_description='Elevation')

        # Create observations in database, so the Analyzer will find them.
        test_observations = [x for x in generate_random_positions()]
        for item in test_observations:
            recorded_at = item[0]
            location = item[1]
            models.Observation.objects.create(
                recorded_at=recorded_at,
                location=location,
                source=source, additional={})

        analyze_subject(str(sub.id))

        for e in Event.objects.all():
            self.assertTrue(e.event_details.all().exists())

        for e in Event.objects.all():
            for ed in e.event_details.all():
                print('Event Details: %s' % ed.data)
