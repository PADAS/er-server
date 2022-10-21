from django.contrib.auth.models import Permission

import observations.views as views
from accounts.models.permissionset import PermissionSet
from accounts.models.user import User
from core.tests import BaseAPITest
from observations.models import SourceGroup, Subject, Observation


class AdditionalTestCase(BaseAPITest):
    fixtures = [
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
        'test/user_and_usergroup.yaml',
        'test/source_group.json'
    ]

    def setUp(self):
        super().setUp()
        self.gps_user = User.objects.get(username='gps-user')
        self.satellite_user = User.objects.get(username='satellite-user')
        self.junkie = Subject.objects.get(name='Junkie')
        self.henry = Subject.objects.get(name='Henry')

    def test_source_group(self):
        request = self.factory.get(self.api_base + '/subjects/')
        self.force_authenticate(request, self.satellite_user)

        response = views.SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        # Check fixture's subject id == response's subject id
        self.assertTrue(any(str(self.henry.id) == subject.get('id')
                            for subject in response.data))

        # Check accessibility of observations for subject
        track_request = self.factory.get(self.api_base + '/{}/tracks/'.format(
            self.henry.id))
        self.force_authenticate(track_request, self.satellite_user)

        response = views.SubjectTracksView.as_view()(track_request,
                                                     subject_id=self.henry.id)
        self.assertEqual(response.status_code, 200)

        # Check observations should be there
        coordinates = response.data['features'][0]['geometry']['coordinates']
        self.assertTrue(len(coordinates) > 0)

        # Henry has observations of junk-fix-source source,
        # but satellite-user don't have permission to access those observation
        observations = [obs.location.coords for obs in
                        Observation.objects.filter(
                            source__manufacturer_id="junk-fix-source")]
        self.assertFalse(any(obs in coordinates for obs in observations))

    def test_multiple_source_observations_for_single_subject(self):
        request = self.factory.get(self.api_base + '/subjects/')
        self.force_authenticate(request, self.gps_user)
        response = views.SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(str(self.junkie.id) == subject.get('id')
                            for subject in response.data))

        # Junkie has observations linked with junk-fix-source & awt sources
        # but satellite-user don't have permission to access awt's observation
        request = self.factory.get(self.api_base + '/{}/tracks/'.format(
            self.junkie.id))
        self.force_authenticate(request, self.satellite_user)
        response = views.SubjectTracksView.as_view()(request,
                                                     subject_id=self.henry.id)
        self.assertEqual(response.status_code, 200)
        coordinates = response.data['features'][0]['geometry']['coordinates']
        observations = [obs.location.coords for obs in
                        Observation.objects.filter(
                            source__manufacturer_id="awt")]
        self.assertFalse(any(obs in coordinates for obs in observations))

        # Junkie can't access all observations linked with junk-fix-source
        # It was linked for some time period and than de-linked
        observations_count = Observation.objects.filter(
            source__manufacturer_id='junk-fix-source').count()
        self.assertTrue(len(coordinates) < observations_count)

    def test_source_not_linked_with_any_source_group(self):
        # Get subjects and observations (gps-user & staellite-user can access)
        # check any subject has observations linked with awt source
        coordinates = []
        for user in [self.gps_user, self.satellite_user]:
            request = self.factory.get(self.api_base + '/subjects/')
            self.force_authenticate(request, user)
            response = views.SubjectsView.as_view()(request)
            for subject in response.data:
                track_request = self.factory.get(
                    self.api_base + '/{}/tracks/'.format(subject.get('id'))
                )
                self.force_authenticate(track_request, user)
                observations = views.SubjectTracksView.as_view()(
                    request, subject_id=subject.get('id'))
                observations = observations.data['features'][0]['geometry']['coordinates']
                coordinates.append(observations)
        awt_observations = [obs.location.coords for obs in
                            Observation.objects.filter(
                                source__manufacturer_id="awt")]
        self.assertFalse(any(obs in coordinates for obs in awt_observations))
