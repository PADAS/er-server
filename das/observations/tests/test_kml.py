import copy
import io
import json
import re
import zipfile
from unittest import mock
from urllib.parse import urlencode

import pytz
from core.tests import BaseAPITest
from datetime import datetime, timedelta
from django.contrib.auth.models import Permission
from django.urls import reverse, resolve
from lxml import etree

import xmlunittest
from accounts.models import User, PermissionSet
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Region, Observation
from observations.views import KmlSubjectView, KmlSubjectsView, KmlRootView, \
    get_subjects_with_observations_in_daterange
from observations.kmlutils import get_kml_access_token
from tracking.models.plugin_base import Obs


def mock_now():
    now = datetime.now()
    return pytz.utc.localize(now - timedelta(weeks=55))


class ObservationTestCase(BaseAPITest, xmlunittest.XmlTestMixin):

    observation_data = [
        (1, 1, 1508520145),
        (1, 2, 1508520146),
        (2, 2, 1508520147)
    ]

    simplekml_default_ids = ('link', 'geom', 'feat', 'substyle', 'time')

    def setUp(self):
        super().setUp()
        # Create a single user with perms to see everything
        self.user = User.objects.create_user(
            'all_perms_user', 'das_all_perms@vulcan.com', 'all_perms_user',
            last_name='Last', first_name='First')

        Region.objects.create(region='Region 1', country='USA')
        Region.objects.create(region='Region 2', country='USA')

        # Create three elephants in two different regions
        self.elephant_1 = Subject.objects.create_subject(id='d2ed403e-9419-41aa-8fa9-45a70e5ce2ef', name='Elephant 1',
                                                         subject_subtype_id='elephant',
                                                         additional={'region': 'Region 1', 'country': 'USA',
                                                                     'rgb': '220,30,30'})
        self.elephant_2 = Subject.objects.create_subject(id='c25e17d0-0337-4f0c-9274-25e5ae4da7c8', name='Elephant 2',
                                                         subject_subtype_id='elephant',
                                                         additional={'region': 'Region 1', 'country': 'USA'})
        self.elephant_3 = Subject.objects.create_subject(id='a873e49c-1cb5-4ad4-b29d-e4b8931036ba', name='Elephant 3',
                                                         subject_subtype_id='elephant',
                                                         additional={'region': 'Region 2', 'country': 'USA'})

        # Put these elephants in a group so we can give permissions to see them
        self.group = SubjectGroup.objects.create(name='elephants')
        self.elephant_1.groups.add(self.group)
        self.elephant_2.groups.add(self.group)
        self.elephant_3.groups.add(self.group)

        # Make the permission set
        self.view_subject_perm = Permission.objects.get(
            codename='view_subject')
        self.view_group_perm = Permission.objects.get_by_natural_key(
            'view_subjectgroup', 'observations', 'subjectgroup')
        self.end_perm = Permission.objects.get(codename='access_ends_0')
        self.start_perm = Permission.objects.get(codename='access_begins_60')

        self.permission_set = PermissionSet.objects.create(name='permissions')
        self.permission_set.permissions.add(
            self.end_perm, self.view_subject_perm, self.view_group_perm)
        self.permission_set.permissions.add(
            self.start_perm, self.view_subject_perm, self.view_group_perm)

        # Now grant the user permissions to see the elephants
        self.group.permission_sets.add(self.permission_set)
        self.group.save()

        self.user.permission_sets.add(self.permission_set)
        self.user.save()

        # Add observations to one of the elephants
        source_args = {
            'subject': {'name': str(self.elephant_1.id)},
            'provider': 'test_provider',
            'manufacturer_id': 'best_manufacturer'
        }
        self.collar_1 = Source.objects.ensure_source(**source_args)
        self.ss_1 = SubjectSource.objects.ensure(
            subject=self.elephant_1, source=self.collar_1)

        for obs_data in self.observation_data:
            recorded_at = datetime.fromtimestamp(obs_data[2], tz=pytz.utc)
            observation = Obs(source=self.collar_1, recorded_at=recorded_at,
                              latitude=obs_data[0], longitude=obs_data[1], additional={})
            Observation.objects.add_observation(observation)

    # Why this isn't built in, I'll never know but
    def elements_equal(self, e1, e2):
        self.assertEqual(e1.tag, e2.tag)
        self.assertEqual(e1.text, e2.text)
        self.assertEqual(e1.tail, e2.tail)
        self.assertEqual(len(e1), len(e2))

        if e1.attrib != e2.attrib:
            # simplekml puts a serial number on all elements it creates. This
            # serial number continues to increment as long as the app runs.
            # Don't let an unexpected serial number fail a comparison of two
            # otherwise equal kml documents
            e1_id = e1.attrib.get('id', '').split('_')[0]
            self.assertIn(e1_id, self.simplekml_default_ids)

        return all(self.elements_equal(c1, c2) for c1, c2 in zip(e1, e2))

    def save_kml(self, kml, filename):
        tree = etree.ElementTree(kml)
        tree.write(filename, pretty_print=True)

    def save_kmz(self, kmz_bytes, filename):
        with open(filename, "wb") as output:
            output.write(kmz_bytes)

    def test_export_all_subjects(self):

        url = reverse('subjects-kml-view')

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlSubjectsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

        # response should be kmz = zip file containing kml
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()

        root = self.assertXmlDocument(response_kml)
        self.assertXmlNamespace(root, None, 'http://www.opengis.net/kml/2.2')

    def test_export_single_subject(self):

        url = reverse('subject-kml-view', kwargs=dict(id=self.elephant_1.id,))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlSubjectView.as_view()(request, id=str(self.elephant_1.id))
        response_data = response.data
        self.assertEqual(response.status_code, 200)

        # response should be kmz = zip file containing kml
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()

        root = self.assertXmlDocument(response_kml)
        self.assertXmlNamespace(root, None, 'http://www.opengis.net/kml/2.2')

    def test_single_subject_authed_url(self):

        id_str = str(self.elephant_1.id)
        url = '{}?auth={}'.format(reverse('subject-kml-view', kwargs=dict(id=id_str,)),
                                  get_kml_access_token(self.user))

        # url = '/api/v1.0/subject/{0}/kml?auth={1}'.format(
        #     self.elephant_1.id, self.user.get_kml_access_token())

        request = self.factory.get(self.api_base + url)
        # Typically we'd force authenticate, but we're testing the workflow
        # _without_ this sort of auth. Leaving this here but commented out so I
        # can make this note to not add it in accidentally later on
        #
        # *** DON'T UNCOMMENT THIS ***
        # self.force_authenticate(request, self.user)

        view = KmlSubjectView.as_view()
        id_str = str(self.elephant_1.id)
        response = view(request, id=id_str)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

        # response should be kmz = zip file containing kml
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()

        root = self.assertXmlDocument(response_kml)
        self.assertXmlNamespace(root, None, 'http://www.opengis.net/kml/2.2')

    def test_master_link(self):
        url = reverse('subjects-kml-root-view')

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        root = self.assertXmlDocument(response_kml)
        self.assertXmlNamespace(root, None, 'http://www.opengis.net/kml/2.2')

    def test_root_kml_passes_filters_to_subjects_url(self):
        url = reverse('subjects-kml-root-view')
        kml_filters = {
            'start': '2017-06-12',
            'end': '2019-06-12',
            'include_inactive': 'true'
        }
        url += '?{}'.format(urlencode(kml_filters))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        root = self.assertXmlDocument(response_kml)
        self.assertXmlNamespace(root, None, 'http://www.opengis.net/kml/2.2')
        response_kml_str = response_kml.decode('utf-8')
        self.assertIn('start=2017-06-12', response_kml_str)
        self.assertIn('end=2019-06-12', response_kml_str)
        self.assertIn('include_inactive=true', response_kml_str.lower())

    def test_not_passing_include_inactive_filter_returns_only_active_subjects(self):
        # force all subjects to be inactive except elephant 1
        for subj in Subject.objects.all():
            if subj.name != 'Elephant 1':
                subj.is_active = False
                subj.save()

        # pass filters to the root kml view
        url = reverse('subjects-kml-root-view')
        url += '?{}'.format(urlencode({'include_inactive': 'false'}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        response_kml_str = response_kml.decode('utf-8')
        urls = re.findall(
            r'http://testserver[\'"]?([^\'" <]+)', response_kml_str)
        subjects_url = urls[0].replace("amp;", "")
        # remove the query params to test if the right view is called
        base_url = subjects_url.split("?")[0]
        # assert that the link passed in the root url redirects to the
        # KmlSubjectsView
        found = resolve(base_url)
        self.assertEqual(found.url_name, "subjects-kml-view")

        request = self.factory.get(self.api_base + subjects_url)
        self.force_authenticate(request, self.user)
        response = KmlSubjectsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        response_kml_str = response_kml.decode('utf-8')
        urls = re.findall(r'http://testserver[\'"]?([^\'" <]+)',
                          response_kml_str)

        queryset = Subject.objects.filter(is_active=True)
        queryset = queryset.by_user_subjects(self.user)
        self.assertEqual(len(urls), queryset.count())
        for subj in queryset:
            self.assertIn(str(subj.id), ' '.join(urls))

    def test_include_inactive_filter_returns_all_subjects(self):
        # force all subjects to be inactive
        self.elephant_1.is_active = False
        self.elephant_1.save()

        self.elephant_2.is_active = False
        self.elephant_2.save()

        # pass filters to the root kml view
        url = reverse('subjects-kml-root-view')
        url += '?{}'.format(urlencode({'include_inactive': 'true'}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        response_kml_str = response_kml.decode('utf-8')
        urls = re.findall(
            r'http://testserver[\'"]?([^\'" <]+)', response_kml_str)
        subjects_url = urls[0].replace("amp;", "")
        # remove the query params to test if the right view is called
        base_url = subjects_url.split("?")[0]
        # assert that the link passed in the root url redirects to the
        # KmlSubjectsView
        found = resolve(base_url)
        self.assertEqual(found.url_name, "subjects-kml-view")

        request = self.factory.get(self.api_base + subjects_url)
        self.force_authenticate(request, self.user)
        response = KmlSubjectsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        response_kml_str = response_kml.decode('utf-8')
        urls = re.findall(r'http://testserver[\'"]?([^\'" <]+)',
                          response_kml_str)

        queryset = Subject.objects.all()
        queryset = queryset.by_user_subjects(self.user)
        self.assertEqual(len(urls), queryset.count())

    @mock.patch('django.utils.timezone.now', mock_now)
    def test_filter_by_dates(self):
        source_args = {
            'subject': {'name': str(self.elephant_2.id)},
            'provider': 'test_provider',
            'manufacturer_id': 'best_manufacturer'
        }
        self.collar_2 = Source.objects.ensure_source(**source_args)
        self.ss_1 = SubjectSource.objects.ensure(
            subject=self.elephant_2, source=self.collar_1)

        observations_timestamp = pytz.utc.localize(
            datetime.now() - timedelta(weeks=55)).timestamp()

        observation_data = [
            (1, 1, int(observations_timestamp)),
            (1, 2, int(observations_timestamp)),
            (2, 2, int(observations_timestamp))
        ]
        for obs_data in observation_data:
            recorded_at = datetime.fromtimestamp(obs_data[2], tz=pytz.utc)
            observation = Obs(source=self.collar_1, recorded_at=recorded_at,
                              latitude=obs_data[0], longitude=obs_data[1], additional={})
            observation2 = Obs(source=self.collar_2, recorded_at=recorded_at,
                               latitude=obs_data[0], longitude=obs_data[1],
                               additional={})

            Observation.objects.add_observation(observation)
            Observation.objects.add_observation(observation2)

        start_date = pytz.utc.localize(datetime.now() - timedelta(weeks=60))
        end_date = pytz.utc.localize(datetime.now() - timedelta(weeks=50))

        url = reverse('subjects-kml-root-view')
        url += '?{}'.format(urlencode({'start': start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                                       'end': end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        response_kml_str = response_kml.decode('utf-8')
        urls = re.findall(
            r'http://testserver[\'"]?([^\'" <]+)', response_kml_str)
        subjects_url = urls[0].replace("amp;", "")
        # remove the query params to test if the right view is called
        base_url = subjects_url.split("?")[0]
        # assert that the link passed in the root url redirects to the
        # KmlSubjectsView
        found = resolve(base_url)
        self.assertEqual(found.url_name, "subjects-kml-view")

        request = self.factory.get(self.api_base + subjects_url)
        self.force_authenticate(request, self.user)
        response = KmlSubjectsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        response_kml_str = response_kml.decode('utf-8')
        urls = re.findall(r'http://testserver[\'"]?([^\'" <]+)',
                          response_kml_str)

        queryset = get_subjects_with_observations_in_daterange(
            start_date, end_date)
        expected_subjects = queryset.by_user_subjects(self.user).count()

        self.assertEqual(len(urls), expected_subjects)

    def test_root_kml_accepts_timezone_aware_datetimes(self):
        start_date = pytz.utc.localize(datetime.now() - timedelta(weeks=60))
        end_date = pytz.utc.localize(datetime.now() - timedelta(weeks=50))

        url = reverse('subjects-kml-root-view')
        url += '?{}'.format(urlencode({'start': start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                                       'end': end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_wrong_date_format_returns_400(self):
        url = reverse('subjects-kml-root-view')
        url += '?{}'.format(
            urlencode({'start': '2018-2008-13T05:11:29.096844Z',
                       'end': '2018-08-13T05:11:29.096844Z'}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlRootView.as_view()(request)
        self.assertEqual(response.status_code, 400)
