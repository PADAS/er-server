

from accounts.models import User, PermissionSet
from core.tests import BaseAPITest
from observations.models import SubjectGroup


class TestSubjectGroup(BaseAPITest):
    fixtures = [
        'new_permission_sets.yaml',
        'subject_types.yaml',
        'test/observations_subject_meta_and_track_data.json',
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='Somename', first_name='Joe')
        self.superuser = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **user_const)
        new_user_const = dict(last_name='Othername', first_name='John')
        self.user = User.objects.create_user(
            'username1', 'user@test.com', 'user', is_superuser=False,
            is_staff=True, **new_user_const)
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 60 Days')
        )
        self.subject_group = SubjectGroup.objects.get(
            name='Indian elephant subjet group')
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 60 Days')
        )

    def test_get_subjectgroup_subjects_without_user(self):
        '''
        Test whether the SubjectGroup.get_all_subjects will tolerate a null user.
        '''
        subject_names = [
            subject.name for subject in self.subject_group.get_all_subjects(user=None)
        ]
        self.assertEqual(len(subject_names), 1, msg="Expected subject list does not match actual." )
