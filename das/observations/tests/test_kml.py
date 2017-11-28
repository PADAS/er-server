import copy
import io
import json
import zipfile

from core.tests import BaseAPITest
from datetime import datetime
from django.contrib.auth.models import Permission
from django.core.urlresolvers import reverse
from lxml import etree

from tempfile import NamedTemporaryFile

from accounts.models import User, PermissionSet
from observations.models import Subject, Source, SubjectSource, SubjectGroup, Region, Observation
from observations.views import KmlSubjectView, KmlSubjectsView, KmlMasterSubjectsView
import observations.tests.targets.kml_target_strings as targets
from tracking.models.plugin_base import Obs


class ObservationTestCase(BaseAPITest):

    observation_data = [
        (1, 1, 1508520145),
        (1, 2, 1508520146),
        (2, 2, 1508520147)
    ]

    simplekml_default_ids = ('link', 'geom', 'feat', 'substyle', 'time')

    save_outputs = True

    def setUp(self):
        super().setUp()
        # Create a single user with perms to see everything
        self.user = User.objects.create_user(
            'all_perms_user', 'das_all_perms@vulcan.com', 'all_perms_user',
            last_name='Last', first_name='First')

        Region.objects.create(region='Region 1', country='USA')
        Region.objects.create(region='Region 2', country='USA')

        # Create three elephants in two different regions
        self.elephant_1 = Subject.objects.create_subject(id='d2ed403e-9419-41aa-8fa9-45a70e5ce2ed', name='Elephant 1',
                                                         subject_type='wildlife',
                                                         subject_subtype='elephant',
                                                         additional={'region': 'Region 1', 'country': 'USA',
                                                                     'rgb': '220,30,30'})
        self.elephant_2 = Subject.objects.create_subject(id='c25e17d0-0337-4f0c-9274-25e5ae4da7c8', name='Elephant 2',
                                                         subject_type='wildlife',
                                                         subject_subtype='elephant',
                                                         additional={'region': 'Region 1', 'country': 'USA'})
        self.elephant_3 = Subject.objects.create_subject(id='a873e49c-1cb5-4ad4-b29d-e4b8931036ba', name='Elephant 3',
                                                         subject_type='wildlife',
                                                         subject_subtype='elephant',
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
            observation = Obs(source=self.collar_1, recorded_at=datetime.fromtimestamp(obs_data[2]),
                              latitude=obs_data[0], longitude=obs_data[1], additional={})
            Observation.objects.add_observation(observation)

    # Why this isn't built in, I'll never know but
    def elements_equal(self, e1, e2):
        if e1.tag != e2.tag:
            return False
        if e1.text != e2.text:
            return False
        if e1.tail != e2.tail:
            return False
        if len(e1) != len(e2):
            return False
        if e1.attrib != e2.attrib:
            # simplekml puts a serial number on all elements it creates. This
            # serial number continues to increment as long as the app runs.
            # Don't let an unexpected serial number fail a comparison of two
            # otherwise equal kml documents
            e1_id = e1.attrib.get('id', '').split('_')[0]
            if e1_id not in self.simplekml_default_ids:
                return False

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
        parser = etree.XMLParser(remove_blank_text=True)
        response_xml = etree.XML(response_kml, parser=parser)
        target_string = targets.all_subjects_target.format(
            self.user.get_kml_access_token())
        target_xml = etree.XML(target_string.encode('utf-8'), parser=parser)

        if self.save_outputs:
            self.save_kml(response_xml, 'all_subjects.actual.kml')
            self.save_kmz(response.data, 'all_subjects.actual.kmz')
            self.save_kml(target_xml, 'all_subjects.expected.kml')

        self.assertTrue(self.elements_equal(response_xml, target_xml))

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
        parser = etree.XMLParser(remove_blank_text=True)
        response_xml = etree.XML(response_kml, parser=parser)
        target_xml = etree.XML(
            targets.single_subject_target.encode('utf-8'), parser=parser)

        if self.save_outputs:
            self.save_kml(response_xml, 'single_subject.actual.kml')
            self.save_kmz(response.data, 'single_subject.actual.kmz')
            self.save_kml(target_xml, 'single_subject.expected.kml')

        self.assertTrue(self.elements_equal(response_xml, target_xml))

    def test_single_subject_authed_url(self):

        id_str = str(self.elephant_1.id)
        url = '{}?auth={}'.format(reverse('subject-kml-view', kwargs=dict(id=id_str,)),
                                  self.user.get_kml_access_token())

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
        parser = etree.XMLParser(remove_blank_text=True)
        response_xml = etree.XML(response_kml, parser=parser)
        target_xml = etree.XML(
            targets.single_subject_target.encode('utf-8'), parser=parser)

        if self.save_outputs:
            self.save_kml(response_xml, 'authed_single_subject.actual.kml')
            self.save_kmz(response.data, 'authed_single_subject.actual.kmz')
            self.save_kml(target_xml, 'authed_single_subject.expected.kml')

        self.assertTrue(self.elements_equal(response_xml, target_xml))

    def test_master_link(self):
        url = reverse('subjects-kml-master-view')

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = KmlMasterSubjectsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

        kmz = zipfile.ZipFile(io.BytesIO(response_data), "r")
        with kmz.open('document.kml') as response_kml_bytes:
            response_kml = response_kml_bytes.read()
        parser = etree.XMLParser(remove_blank_text=True)
        response_xml = etree.XML(response_kml, parser=parser)
        target_string = targets.master_link_target.format(
            self.user.get_kml_access_token())
        target_xml = etree.XML(target_string.encode('utf-8'), parser=parser)

        if self.save_outputs:
            self.save_kml(response_xml, 'master_file.actual.kml')
            self.save_kmz(response.data, 'master_file.actual.kmz')
            self.save_kml(target_xml, 'master_file.expected.kml')

        self.assertTrue(self.elements_equal(response_xml, target_xml))
