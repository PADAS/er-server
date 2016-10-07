from django.test import TestCase

from accounts.models import User
import random
import json
import string

class TestReports(TestCase):

    fixtures = 'oauth_clients'

    pwd = ''.join(random.SystemRandom().choice((string.ascii_uppercase + string.ascii_lowercase + string.digits)) for _ in range(12))
    user_data = dict(username='sometestuser', password=pwd, email='testuser@tempuri.org', is_superuser=True,
                     first_name='Some',
                     last_name='Testuser')

    login_data = dict(grant_type='password',
                      username=user_data['username'],
                      password=user_data['password'],
                      client_id='das_web_client')

    def setUp(self):

        User.objects.create_superuser(**self.user_data)



    def test_sitrep(self):

        response = self.client.post('/oauth2/token', data=self.login_data)

        self.assertEqual(response.status_code, 200)

        body = json.loads(str(response.content, 'utf8'))
        self.assertTrue(body['access_token'] is not None)

        extras = dict(Authorization='Bearer {}'.format(body['access_token']))
        response = self.client.get('/api/v1.0/reports/sitrep.docx', follow=True, **extras)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.using, 'docx_template')
        self.assertTemplateUsed('lewa_sitrep_template.docx')
