import os
import django.contrib.auth
from django.urls import reverse
from django.db import transaction
from core.tests import BaseAPITest
from unittest import mock
from accounts.models import PermissionSet
from observations.models import Subject, SubjectGroup, Source, SubjectSource, SourceProvider
from observations.views import MessagesView, SubjectView
from urllib.parse import urlencode

User = django.contrib.auth.get_user_model()


class MessagesTestCase(BaseAPITest):
    fixtures = [
        'test/sourceprovider.yaml',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json'
    ]

    def setUp(self):
        super().setUp()
        self.test_subject = Subject.objects.first()

        self.admin_user = User.objects.create_superuser(username="superuser",
                                                        password="adfsfds32423",
                                                        email="super@user.com")

        self.app_user.permission_sets.add(PermissionSet.objects.get(name='View Message Permission'))

    @mock.patch('observations.tasks.handle_outbox_message.apply_async')
    def test_send_outbox_message(self, mock_send):
        message_data = dict(text="Status?")
        url = reverse('messages-view')
        url += '?{}'.format(urlencode({'subject_id': self.test_subject.id,
                                       'source_id': self.test_subject.source.id}))

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
         self.assertTrue(mock_send.called)
        assert response.status_code == 201

    def test_send_inbox_message(self):
        message_data = dict(text="Status?", message_type="inbox")
        url = reverse('messages-view')

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 400
        assert response.data == {
            'Error': 'Manufacturer Id param has to be provided for an inbox message'}

        url += '?{}'.format(urlencode({'manufacturer_id': 'subject-status-1'}))

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 201

    @mock.patch('observations.tasks.handle_outbox_message.apply_async')
    def test_messaging_in_subject_payload(self, mock_send):
        url = reverse('subject-view', args=[self.test_subject.id, ])
        request = self.factory.get(url)
        self.force_authenticate(request, self.admin_user)
        response = SubjectView.as_view()(request, id=str(self.test_subject.id))
        self.assertEqual(response.status_code, 200)
        messaging = response.data.get("messaging")[0]

        assert messaging.get('source_provider') == "Default"
        assert messaging.get(
            'url') == "http://testserver/api/v1.0/messages?subject_id=269524d5-a434-4377-9ea9-2a7946dbd9c4&source_id=56b1cf14-ef97-4054-8fbd-1342f265b2a9"

        # Post a message to the subject using url given in the payload
        message_data = dict(text="Left the outpost?")
        url = messaging.get('url')

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        self.assertTrue(mock_send.called)
        self.assertEqual(response.status_code, 201)

    @mock.patch('observations.tasks.handle_outbox_message.apply_async')
    def test_message_permission(self, mock_send):
        with mock.patch('django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block', lambda x: False):
            subject = Subject.objects.create(name='radio-001', )
            subject_group = SubjectGroup.objects.create(name='Radios')
            subject_group.subjects.set([subject])
            transaction.get_connection().run_and_clear_commit_hooks()
            permission_set = subject_group.permission_sets.get(name=subject_group.auto_permissionset_name)
            self.assertEqual(permission_set.name, subject_group.auto_permissionset_name)

            provider = SourceProvider.objects.create(provider_key='RDO-provider')
            source = Source.objects.create(manufacturer_id='3FG89', provider=provider)
            SubjectSource.objects.create(subject=subject, source=source)

            # send outbox message.
            url = reverse('messages-view')
            url += '?{}'.format(urlencode({'subject_id': subject.id, 'source_id': subject.source.id}))

            request = self.factory.post(url, data=dict(text="Hey, there!"))
            self.force_authenticate(request, self.admin_user)
            response = MessagesView.as_view()(request)
            self.assertTrue(mock_send.called)
            assert response.status_code == 201

            # return 403 (Forbidden) for user with no message permission.
            request = self.factory.post(url, data=dict(text="Hey, I dont have permission to send message."))
            self.force_authenticate(request, self.app_user)
            response = MessagesView.as_view()(request)
            assert response.status_code == 403

            # User can only see messages for subject-groups they have permission for.
            url = reverse('messages-view')
            request = self.factory.get(url)
            self.force_authenticate(request, self.app_user)
            response = MessagesView.as_view()(request)
            self.assertEqual(len(response.data['results']), 0)
