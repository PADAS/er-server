import os
import django.contrib.auth
from django.urls import reverse
from core.tests import BaseAPITest
from observations.models import Subject
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

    def test_send_outbox_message(self):
        message_data = dict(text="Status?")
        url = reverse('messages-view')
        url += '?{}'.format(urlencode({'subject_id': self.test_subject.id,
                            'source_id': self.test_subject.source.id}))

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.app_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 201

    def test_send_inbox_message(self):
        message_data = dict(text="Status?", message_type="inbox")
        url = reverse('messages-view')

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.app_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 400
        assert response.data == {
            'Error': 'Manufacturer Id param has to be provided for an inbox message'}

        url += '?{}'.format(urlencode({'manufacturer_id': 'subject-status-1'}))

        request = self.factory.post(url, data=message_data)
        self.force_authenticate(request, self.app_user)
        response = MessagesView.as_view()(request)
        assert response.status_code == 201

    def test_messaging_in_subject_payload(self):
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
        self.force_authenticate(request, self.app_user)
        response = MessagesView.as_view()(request)
        self.assertEqual(response.status_code, 201)
