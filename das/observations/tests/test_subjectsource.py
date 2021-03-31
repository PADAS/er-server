import random

from django.test import TestCase
from drf_extra_fields.compat import DateTimeTZRange
from datetime import datetime, timedelta
import pytz
from observations.models import Subject, Source, SubjectSource, SourceProvider, DEFAULT_ASSIGNED_RANGE, SubjectStatus
from observations.serializers import ObservationSerializer


class SubjectSourceTestCase(TestCase):

    fixtures = [
        'test/sourceprovider.yaml',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
    ]

    def setUp(self):
        pass

    def generate_observation_data(self, subject_id, source_id):

        # Generate random data for observation
        observation_time = pytz.UTC.localize(datetime.now())
        latitude = float(random.randint(3000, 3000)) / 100
        longitude = float(random.randint(2800, 4000)) / 100

        location = dict(longitude=longitude, latitude=latitude)

        observation = {
            'location': location,
            'recorded_at': observation_time,
            'source': source_id,
            'additional': {}
        }
        serializer = ObservationSerializer(data=observation)
        if serializer.is_valid():
            observation = serializer.save()

        subject_statuses = SubjectStatus.objects.filter(subject__subjectsource__source_id=source_id,
                                                        delay_hours=0)

        subject_status = subject_statuses.first()
        return subject_status, longitude, latitude

    def test_subjectsource_with_empty_assignedrange(self):
        # test that we don't have empty assignedaterange set in database.

        subject, created = Subject.objects.get_or_create(
            name='Assigned Subject')
        provider, created = SourceProvider.objects.get_or_create(
            provider_key='assignment-test-provider')
        source, created = Source.objects.get_or_create(manufacturer_id='assignment-test-01',
                                                       provider=provider)

        ss = SubjectSource.objects.create(
            subject=subject, source=source, assigned_range='empty')

        ss.refresh_from_db()
        assert not ss.assigned_range.isempty  # there is default lower & upper values

        sample_date = datetime.now(tz=pytz.utc)

        assert sample_date in ss.assigned_range
        assert sample_date not in ss.safe_assigned_range

        SubjectSource.objects.filter(id=ss.id).update(
            assigned_range=DEFAULT_ASSIGNED_RANGE)

        ss = SubjectSource.objects.get(id=ss.id)
        assert ss.safe_assigned_range.lower == DEFAULT_ASSIGNED_RANGE[0]
        assert ss.safe_assigned_range.upper == DEFAULT_ASSIGNED_RANGE[1]

    def test_update_source(self):

        subject_id = '269524d5-a434-4377-9ea9-2a7946dbd9c4'
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'
        source_id2 = 'a91e0366-898c-475b-830f-e0fae46e6efe'

        subject_status, longitude, latitude = self.generate_observation_data(
            subject_id=subject_id, source_id=source_id)
        self.assertEqual(
            (subject_status.location.x, subject_status.location.y),
            (longitude, latitude))

        subject_status, longitude, latitude = self.generate_observation_data(
            subject_id=subject_id, source_id=source_id2)
        self.assertEqual(
            (subject_status.location.x, subject_status.location.y),
            (longitude, latitude))

    def test_subjectsource_with_only_lower_bound_assignedrange(self):

        subject, created = Subject.objects.get_or_create(name='#01-subject')
        provider, created = SourceProvider.objects.get_or_create(provider_key='#01-provider')

        source, created = Source.objects.get_or_create(manufacturer_id='#01-manufacurer_id', provider=provider)

        ss = SubjectSource.objects.create(subject=subject, source=source,
                                          assigned_range=DateTimeTZRange(lower=DEFAULT_ASSIGNED_RANGE[0]))
        ss.refresh_from_db()
        self.assertTrue(ss.assigned_range.lower)
        self.assertTrue(ss.assigned_range.upper)
