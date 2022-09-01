from datetime import datetime
from unittest import mock
from urllib.parse import urlencode

from drf_extra_fields.fields import DateTimeTZRange

import django.contrib.auth
from django.db import transaction
from django.urls import reverse

from accounts.models import PermissionSet
from accounts.views import UserView
from core.tests import BaseAPITest
from observations import models
from observations.message_adapters import _handle_outbox_message
from observations.models import (Source, SourceProvider, Subject, SubjectGroup,
                                 SubjectSource)
from observations.views import MessagesView, SubjectView

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

        self.app_user.permission_sets.add(
            PermissionSet.objects.get(name='View Message Permission'))
        models.SourceProvider.objects.filter(display_name='Default').update(
            additional={"two_way_messaging": True})

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
        assert response.data.get('status') == 'received'

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
            permission_set = subject_group.permission_sets.get(
                name=subject_group.auto_permissionset_name)
            self.assertEqual(permission_set.name,
                             subject_group.auto_permissionset_name)

            provider = SourceProvider.objects.create(
                provider_key='RDO-provider')
            source = Source.objects.create(
                manufacturer_id='3FG89', provider=provider)
            SubjectSource.objects.create(subject=subject, source=source)

            # send outbox message.
            url = reverse('messages-view')
            url += '?{}'.format(urlencode({'subject_id': subject.id,
                                'source_id': subject.source.id}))

            request = self.factory.post(url, data=dict(text="Hey, there!"))
            self.force_authenticate(request, self.admin_user)
            response = MessagesView.as_view()(request)
            self.assertTrue(mock_send.called)
            assert response.status_code == 201

            # permission exposed thru API.
            url_user = 'api/v1.0/user/me'
            request = self.factory.get(url_user)
            self.force_authenticate(request, self.admin_user)
            response = UserView.as_view()(request, id=self.admin_user.id)
            assert response.status_code == 200
            assert 'view' in response.data['permissions']['message']

            # return 403 (Forbidden) for user with no message permission.
            request = self.factory.post(url, data=dict(
                text="Hey, I dont have permission to send message."))
            self.force_authenticate(request, self.app_user)
            response = MessagesView.as_view()(request)
            assert response.status_code == 403

            # User can only see messages for subject-groups they have permission for.
            url = reverse('messages-view')
            request = self.factory.get(url)
            self.force_authenticate(request, self.app_user)
            response = MessagesView.as_view()(request)
            self.assertEqual(len(response.data['results']), 0)
        self.assertTrue(mock_send.called)

    def get_subject(self, subject_id):
        url = reverse('subject-view', args=[subject_id, ])
        request = self.factory.get(url)
        self.force_authenticate(request, self.admin_user)
        response = SubjectView.as_view()(request, id=str(subject_id))
        return response

    def test_subject_api_with_msg_capabilities(self):
        subject = Subject.objects.create(name='#subject-001')
        provider = models.SourceProvider.objects.create(
            provider_key='#01-provider')
        source = models.Source.objects.create(
            manufacturer_id='#01-manufacurer_id', provider=provider)

        subject_source = models.SubjectSource.objects.create(subject=subject, source=source,
                                                             assigned_range=DateTimeTZRange(lower=models.DEFAULT_ASSIGNED_RANGE[0]))

        # subject with source-provider that has two-way messaging disabled (default).
        response = self.get_subject(subject.id)
        self.assertEqual(response.status_code, 200)
        assert response.data.get("messaging") is None

        # enable two-way messaging for source-provider
        provider.additional = {"two_way_messaging": True}
        provider.save()
        response = self.get_subject(subject.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('messaging'))

        # disable two-way messaging for source-provider and enable source two-way messaging.
        # should still have two-way messaging disabled.
        provider.additional = {"two_way_messaging": False}
        provider.save()
        source.additional = {'two_way_messaging': True}
        source.save()
        response = self.get_subject(subject.id)
        self.assertEqual(response.status_code, 200)
        assert response.data.get("messaging") is None

        # enable two-way messaging for source-provider and disable source two-way messaging.
        # messaging-should be disabled.
        provider.additional = {"two_way_messaging": True}
        provider.save()
        source.additional = {'two_way_messaging': False}
        source.save()
        response = self.get_subject(subject.id)
        self.assertEqual(response.status_code, 200)
        assert response.data.get("messaging") is None

        # enable two-way messaging for source-provider and source two-way messaging to be empty string.
        # messaging-should be enabled..
        provider.additional = {"two_way_messaging": True}
        provider.save()
        source.additional = {'two_way_messaging': ''}
        source.save()
        response = self.get_subject(subject.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('messaging'))

        # enable two-way messaging for source-provider and source two-way messaging to be None.
        # messaging-should be enabled..
        provider.additional = {"two_way_messaging": True}
        provider.save()
        source.additional = {'two_way_messaging': None}
        source.save()
        response = self.get_subject(subject.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('messaging'))

    def test_fetchmost_recent_message(self):
        urlpath = reverse('messages-view')
        url = urlpath + \
            '?{}'.format(urlencode({'manufacturer_id': 'subject-status-1'}))
        request = self.factory.post(url, data=dict(
            text="Sending inbox message", message_type="inbox"))
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 201

        request = self.factory.post(url, data=dict(
            text="Sending second message", message_type="inbox"))
        self.force_authenticate(request, self.admin_user)
        MessagesView.as_view()(request)

        request = self.factory.get(urlpath)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 200
        assert response.data.get('count') == 2

        # get most-recent message.
        url = urlpath + '?{}'.format(urlencode({'recent_message': 1}))
        request = self.factory.get(url)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 200
        assert response.data.get('count') == 1
        assert response.data.get('results')[
            0]['text'] == 'Sending second message'

    @mock.patch('requests.post')
    def test_smart_integrate_adapter(self, mock_request):
        mock_request.return_value = mock.Mock(status_code=200)

        messaging_config = {"url": "https://cdip-api.pamdas.org/messages",
                            "apikey": "asdf89as903rkfmasf9s0801mfae",
                            "adapter_type": "smart-integrate-adapter"
                            }

        subject = Subject.objects.create(name='Smart-radio')
        provider = models.SourceProvider.objects.create(provider_key='Smart-Integrate',
                                                        additional=dict(messaging_config=messaging_config,
                                                                        two_way_messaging=True,))
        source = models.Source.objects.create(
            manufacturer_id='0000001', provider=provider)

        models.SubjectSource.objects.create(subject=subject, source=source,
                                            assigned_range=DateTimeTZRange(lower=models.DEFAULT_ASSIGNED_RANGE[0]))

        message = {
            'sender_id': self.admin_user.id,
            'receiver_id': subject.id,
            'device_id': source.id,
            'text': 'Habari yako!',
            'message_type': 'outbox',
            'message_time': datetime.utcnow()
        }
        msg = models.Message.objects.create(**message)
        assert msg.status == 'pending'

        _handle_outbox_message(
            message_id=msg.id, user_email=self.admin_user.email)
        self.assertTrue(mock_request.called)
        assert models.Message.objects.get(id=msg.id).status == 'sent'

    def test_verify_device_inlcuded_in_message_payload(self):
        message_data = dict(text="new message coming in...",
                            message_type="inbox")
        url = reverse('messages-view')

        url += '?{}'.format(urlencode({'manufacturer_id': 'subject-status-1'}))

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.admin_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 201
        assert response.data.get('device')
