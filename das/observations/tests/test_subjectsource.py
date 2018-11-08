from django.test import TestCase
from datetime import datetime
import pytz
from observations.models import Subject, Source, SubjectSource, SourceProvider, DEFAULT_ASSIGNED_RANGE


class SubjectSourceTestCase(TestCase):

    def setUp(self):
        pass

    def test_subjectsource_with_empty_assignedrange(self):

        subject, created = Subject.objects.get_or_create(
            name='Assigned Subject')
        provider, created = SourceProvider.objects.get_or_create(
            provider_key='assignment-test-provider')
        source, created = Source.objects.get_or_create(manufacturer_id='assignment-test-01',
                                                       provider=provider)

        ss = SubjectSource.objects.create(
            subject=subject, source=source, assigned_range='empty')

        ss.refresh_from_db()
        self.assertTrue(ss.assigned_range.isempty)

        sample_date = datetime.now(tz=pytz.utc)

        self.assertFalse(sample_date in ss.assigned_range)
        self.assertFalse(sample_date in ss.safe_assigned_range)

        SubjectSource.objects.filter(id=ss.id).update(
            assigned_range=DEFAULT_ASSIGNED_RANGE)

        ss = SubjectSource.objects.get(id=ss.id)
        self.assertEqual(ss.safe_assigned_range.lower,
                         DEFAULT_ASSIGNED_RANGE[0], msg='Lower bound does not match.')
        self.assertEqual(ss.safe_assigned_range.upper,
                         DEFAULT_ASSIGNED_RANGE[1], msg='Upper bound does not match.')
