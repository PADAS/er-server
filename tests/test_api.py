from json import loads
from django.contrib.auth.models import User

from rest_framework.test import APITestCase
from rest_framework import status


class BaseAPITestCase(APITestCase):
    user1 = {'username': 'test-user-1', 'password': 'test-pass'}
    user2 = {'username': 'test-user-2', 'password': 'test-pass'}

    def make_api_path(self, path):
        return '/api/v1.0' + '' if path.startswith('/') else '/' + path

    def get_user(self, cred):
        return User.objects.get(username=cred['username'])

    def register(self, cred):
        response = self.client.post('/register/', cred)
        return response

    def get_token(self, cred):
        data = {'grant_type':'password', 'username':cred['username'],
        'password':cred['password'], 'client_id':cred['username']}

        response = self.client.post('/oauth2/access_token', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = loads(response.content)

        self.assertTrue('access_token' in response_data)
        token = response_data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

    def reg_token(self, cred):
        self.register(cred)
        self.get_token(cred)


class SubjectsTest(BaseAPITestCase):
    def test_subjects(self):
        self.reg_token(self.user1)
        response = self.client.get(self.make_api_path('subjects'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

