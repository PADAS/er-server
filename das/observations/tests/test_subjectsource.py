import datetime
import random
import uuid
from urllib.parse import parse_qs, urlsplit

import pytz
from drf_extra_fields.fields import DateTimeTZRange
from faker import Faker

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status

from accounts.models import PermissionSet, User
from core.tests import BaseAPITest
from observations.models import (DEFAULT_ASSIGNED_RANGE,
                                 LatestObservationSource, Source,
                                 SourceProvider, Subject, SubjectGroup,
                                 SubjectSource, SubjectStatus)
from observations.serializers import ObservationSerializer
from observations.utils import parse_comma
from observations.views import (ObservationView, SourcesView, SourceView,
                                SubjectSourcesAssignmentView)

User = get_user_model()


def generate_observation_data(source_id):
    # Generate random data for observation
    observation_time = pytz.UTC.localize(datetime.datetime.now())
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


class SubjectSourceTestCase(BaseAPITest):
    fixtures = [
        'test/sourceprovider.yaml',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
    ]

    def setUp(self):
        super().setUp()
        self.user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **self.user_const)

        self.non_superuser = User.objects.create_user(username='user_x',
                                                      email='user_x@test.com',
                                                      password=User.objects.make_random_password(),
                                                      **self.user_const)

    def test_subjectsource_with_empty_assignedrange(self):
        # test that we don't have empty assignedaterange set in database.

        subject, created = Subject.objects.get_or_create(
            name='Assigned Subject')
        provider, created = SourceProvider.objects.get_or_create(
            provider_key='assignment-test-provider')
        source, created = Source.objects.get_source(manufacturer_id='assignment-test-01',
                                                    provider=provider)

        ss = SubjectSource.objects.create(
            subject=subject, source=source, assigned_range='empty')

        ss.refresh_from_db()
        assert not ss.assigned_range.isempty  # there is default lower & upper values

        sample_date = datetime.datetime.now(tz=pytz.utc)

        assert sample_date in ss.assigned_range
        assert sample_date not in ss.safe_assigned_range

        SubjectSource.objects.filter(id=ss.id).update(
            assigned_range=DEFAULT_ASSIGNED_RANGE)

        ss = SubjectSource.objects.get(id=ss.id)
        assert ss.safe_assigned_range.lower == DEFAULT_ASSIGNED_RANGE[0]
        assert ss.safe_assigned_range.upper == DEFAULT_ASSIGNED_RANGE[1]

    def test_update_source(self):
        source_id = '56b1cf14-ef97-4054-8fbd-1342f265b2a9'
        source_id2 = 'a91e0366-898c-475b-830f-e0fae46e6efe'

        subject_status, longitude, latitude = generate_observation_data(
            source_id=source_id)
        self.assertEqual(
            (subject_status.location.x, subject_status.location.y),
            (longitude, latitude))

        subject_status, longitude, latitude = generate_observation_data(
            source_id=source_id2)
        self.assertEqual(
            (subject_status.location.x, subject_status.location.y),
            (longitude, latitude))

    def test_subjectsource_with_only_lower_bound_assignedrange(self):
        subject, created = Subject.objects.get_or_create(name='#01-subject')
        provider, created = SourceProvider.objects.get_or_create(
            provider_key='#01-provider')

        source, created = Source.objects.get_or_create(
            manufacturer_id='#01-manufacurer_id', provider=provider)

        ss = SubjectSource.objects.create(subject=subject, source=source,
                                          assigned_range=DateTimeTZRange(lower=DEFAULT_ASSIGNED_RANGE[0]))
        ss.refresh_from_db()
        self.assertTrue(ss.assigned_range.lower)
        self.assertTrue(ss.assigned_range.upper)

    def test_parse_comma_function(self):
        # pass comma-separated values(str)
        urlpath = 'test.pamdas.org/api/v1.0/sources?manufacturer_id=Garmin-001,Garmin-002,Garmin-005'

        query = urlsplit(urlpath).query
        params = parse_qs(query)
        listed_manufacturer_id = parse_comma(params.get('manufacturer_id')[0])

        self.assertEqual(listed_manufacturer_id, [
                         'Garmin-001', 'Garmin-002', 'Garmin-005'])

        # pass comma-separated values (UUD4)
        urlpath2 = 'test.pamdas.org/api/v1.0/' \
                   'sources?id=0d9725c0-c186-464f-98f4-a45d31f81efd,0a308294-7b80-4633-a967-ef4f8e1de79a'

        query = urlsplit(urlpath2).query
        params = parse_qs(query)
        listed_source_id = parse_comma(params.get('id')[0])

        self.assertEqual(listed_source_id, [uuid.UUID('0d9725c0-c186-464f-98f4-a45d31f81efd'),
                                            uuid.UUID('0a308294-7b80-4633-a967-ef4f8e1de79a')])

    def test_sources_api(self):
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key='#01-provider')
        provider2, _ = SourceProvider.objects.get_or_create(
            provider_key='#02-provider')  # control

        source, _ = Source.objects.get_or_create(id=uuid.UUID('1f199c72-7a52-4659-be86-4ac40231826f'),
                                                 manufacturer_id='#01-manufacurer_id', provider=provider)

        source2, _ = Source.objects.get_or_create(id=uuid.UUID('7cbbd57e-0026-46a2-9726-32849a527326'),
                                                  manufacturer_id='#02-manufacurer_id', provider=provider)

        source3, _ = Source.objects.get_or_create(
            manufacturer_id='#02-Manf-ID', provider=provider2)

        # Two sources with provider-key: #01-prvider
        urlpath = reverse('sources-view')
        url = urlpath + f'?provider=#01-provider'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SourcesView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 2)

        # there is only one source provider-key: #01-provider.
        url = urlpath + f'?provider=#02-provider'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SourcesView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 1)

        # filter by source_id:
        url = urlpath + f'?id=7cbbd57e-0026-46a2-9726-32849a527326, 1f199c72-7a52-4659-be86-4ac40231826f'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SourcesView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 2)

    def test_subjectsources_api(self):
        """Test Subject-Sources-Assignment-API"""
        SubjectSource.objects.all().delete()

        subject, created = Subject.objects.get_or_create(name='#01-subject')
        subject2, created = Subject.objects.get_or_create(name='#02-subject')

        provider, created = SourceProvider.objects.get_or_create(
            provider_key='#01-provider')

        source, created = Source.objects.get_or_create(
            manufacturer_id='#01-manufacurer_id', provider=provider)
        source2, created = Source.objects.get_or_create(
            manufacturer_id='#02-manufacurer_id', provider=provider)
        source3, created = Source.objects.get_or_create(
            manufacturer_id='#03-manufacurer_id', provider=provider)

        # assign subject (#01-subject) with different sources.
        ss = SubjectSource.objects.create(subject=subject, source=source,
                                          assigned_range=DateTimeTZRange(lower=DEFAULT_ASSIGNED_RANGE[0]))
        ss2 = SubjectSource.objects.create(subject=subject, source=source2,
                                           assigned_range=DateTimeTZRange(lower=DEFAULT_ASSIGNED_RANGE[0]))

        # asign subject (#02-subject) only one source.
        ss3 = SubjectSource.objects.create(subject=subject2, source=source3,
                                           assigned_range=DateTimeTZRange(lower=DEFAULT_ASSIGNED_RANGE[0]))

        ss.refresh_from_db()
        ss2.refresh_from_db()
        ss3.refresh_from_db()

        urlpath = reverse('subject-sources-list-view')
        # all subject-sources;
        request = self.factory.get(urlpath)
        self.force_authenticate(request, self.user)
        response = SubjectSourcesAssignmentView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 3)

        # filter by subject
        url = urlpath + f'?subjects={str(subject.id)}'
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = SubjectSourcesAssignmentView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 2)

        # filter by sources
        url = urlpath + f'?sources={str(source3.id)}, {str(source2.id)}'
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = SubjectSourcesAssignmentView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 2)

        # filter by both subject_id and source_id
        url = urlpath + \
            f'?sources={str(source2.id)}&subjects={str(subject2.id)}'
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = SubjectSourcesAssignmentView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 2)

        # Create Subject-Group & have only one subject & give permission to view subject-source.
        parent_group = SubjectGroup.objects.create(name='SG Group')
        view_subject_group_perm_name = 'view_subjectgroup'
        view_subject_source_perm_name = 'view_subjectsource'

        view_subject_perm = Permission.objects.get(
            codename=view_subject_group_perm_name)
        view_subject_source = Permission.objects.get(
            codename=view_subject_source_perm_name)
        perm_set = PermissionSet.objects.create(name="View SG Group Perm set")
        perm_set2 = PermissionSet.objects.create(
            name="View SubjectSource PermSet")
        perm_set.permissions.add(view_subject_perm)
        perm_set2.permissions.add(view_subject_source)
        perm_set.save()
        perm_set2.save()
        self.non_superuser.permission_sets.add(perm_set)
        self.non_superuser.permission_sets.add(perm_set2)
        self.non_superuser.save()

        parent_group.permission_sets.add(perm_set)
        parent_group.subjects.add(subject2)
        parent_group.is_visible = True
        parent_group.save()

        # non-super-user
        # should only view subject-source (getting all subject-sources).
        request = self.factory.get(urlpath)
        self.force_authenticate(request, self.non_superuser)
        response = SubjectSourcesAssignmentView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 1)

        # non-super-user filtering subject and source he has not permission to view.
        url = urlpath + f'?sources={str(source.id)}&subjects={str(subject.id)}'
        request = self.factory.get(url)
        self.force_authenticate(request, self.non_superuser)
        response = SubjectSourcesAssignmentView.as_view()(request)
        self.assertEqual(len(response.data.get('results')), 0)


class SourceAPITestCase(BaseAPITest):
    use_atomic_transaction = True

    def setUp(self):
        self.user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **self.user_const)
        return super().setUp()

    def test_create_source_api(self):
        faker = Faker()
        subject_count = Subject.objects.count()
        provider_key = f"{faker.last_name()}_{faker.last_name()}"
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key=provider_key)
        source_data = dict(manufacturer_id=faker.last_name(),
                           provider=provider_key, additional={})
        urlpath = reverse('sources-view')
        request = self.factory.post(urlpath, source_data)

        self.force_authenticate(request, self.user)
        response = SourcesView.as_view()(request)
        assert subject_count == Subject.objects.count()
        assert response.status_code == status.HTTP_201_CREATED

    def test_delete_source_api(self):
        faker = Faker()
        provider_key = f"{faker.last_name()}_{faker.last_name()}"
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key=provider_key)
        source_data = dict(manufacturer_id=faker.last_name(),
                           provider=provider_key, additional={})
        urlpath = reverse('sources-view')
        request = self.factory.post(urlpath, source_data)

        self.force_authenticate(request, self.user)
        response = SourcesView.as_view()(request)
        assert response.status_code == status.HTTP_201_CREATED
        source_id = response.data["id"]

        for i in range(500):
            subject_status, longitude, latitude = generate_observation_data(
                source_id=source_id)

        urlpath = reverse('source-view', kwargs={"id": source_id})
        request = self.factory.delete(urlpath)

        self.force_authenticate(request, self.user)
        response = SourceView.as_view()(request, id=source_id)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_observation_api(self):
        faker = Faker()
        provider_key = f"{faker.last_name()}_{faker.last_name()}"
        provider, _ = SourceProvider.objects.get_or_create(
            provider_key=provider_key)
        source_data = dict(manufacturer_id=faker.last_name(),
                           provider=provider_key, additional={})
        urlpath = reverse('sources-view')
        request = self.factory.post(urlpath, source_data)

        self.force_authenticate(request, self.user)
        response = SourcesView.as_view()(request)
        assert response.status_code == status.HTTP_201_CREATED
        source_id = response.data["id"]

        for i in range(50):
            subject_status, longitude, latitude = generate_observation_data(
                source_id=source_id)

        lob = LatestObservationSource.objects.filter(
            source_id=source_id).first()

        urlpath = reverse('observation-view',
                          kwargs={"id": lob.observation.id})
        request = self.factory.delete(urlpath)

        self.force_authenticate(request, self.user)
        response = ObservationView.as_view()(request, id=lob.observation.id)
        assert response.status_code == status.HTTP_204_NO_CONTENT
