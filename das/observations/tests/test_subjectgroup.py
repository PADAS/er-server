from uuid import uuid4

from django.contrib.auth.models import Permission

from accounts.models import User, PermissionSet
from core.tests import BaseAPITest
from observations.admin import SubjectGroupChangeForm
from observations.models import Subject, SubjectGroup
from observations.views import SubjectGroupsView, SubjectsView

API_BASE = '/api/v1.0'


class SubjectGroupTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        subject_view = PermissionSet.objects.create(
            name='subject_view')
        subject_view.permissions.add(Permission.objects.get_by_natural_key(
            'view_subject', 'observations', 'subject'
        ))
        subject_view.permissions.add(Permission.objects.get_by_natural_key(
            'view_subjectgroup', 'observations', 'subjectgroup'
        ))
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user(
            'super', 'super@test.com', 'super', is_staff=True, **user_const)
        self.user.permission_sets.add(subject_view)
        self.user.save()
        # Create both types of subjects(active & inactive)
        self.henry = Subject.objects.create(name='Henry')
        self.rosie = Subject.objects.create(name='Rosie')
        self.alpha = Subject.objects.create(name='Alpha', is_active=False)
        self.beta = Subject.objects.create(name='beta', is_active=False)
        # Create SubjectGroup and link subjects  using SubjectGroupChangeForm
        subject_group_data = {
            "id": uuid4(),
            "name": "Lewa Elephants",
            "active_subjects": [self.henry.id, self.rosie.id],
            "inactive_subjects": [self.alpha.id, self.beta.id],
            "permission_sets": [subject_view],
            "is_visible": True
        }
        form = SubjectGroupChangeForm(data=subject_group_data)
        self.assertTrue(form.is_valid())
        form.save()

    def test_subjectgroup(self):
        subject_group = SubjectGroup.objects.get(name='Lewa Elephants')
        lewa_elephants = subject_group.get_all_subjects()
        # Check inactive subjects are in subject group's subject list
        self.assertTrue(
            self.alpha in lewa_elephants and self.beta in lewa_elephants
        )

    def test_subject_groups_api(self):
        # Test subjectgroups api(lists subjectgroups and linked subjects)
        # whether this api returns inactive subjects of subjectgroups
        request = self.factory.get(API_BASE + '/subjectgroups')
        self.force_authenticate(request, self.user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        subject_ids = []
        for subject_group in response.data:
            for subject in subject_group.get('subjects'):
                subject_ids.append(subject.get('id'))
        self.assertTrue((str(self.alpha.id) not in subject_ids and
                         str(self.beta.id) not in subject_ids) and
                        (str(self.rosie.id) in subject_ids and
                         str(self.henry.id) in subject_ids))

    def test_subjects_api(self):
        # Test subjects api(lists all active subjects)
        # whether this api returns inactive subject/s or not
        request = self.factory.get(API_BASE + '/subjects')
        self.force_authenticate(request, self.user)

        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        subject_ids = []
        for subject in response.data:
            subject_ids.append(subject.get('id'))
        self.assertTrue((str(self.alpha.id) not in subject_ids and
                         str(self.beta.id) not in subject_ids) and
                        (str(self.rosie.id) in subject_ids and
                         str(self.henry.id) in subject_ids))
