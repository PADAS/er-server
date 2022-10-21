from django.test import TestCase

from accounts.models import User
from observations.kmlutils import get_kml_access_token


class UserModelTest(TestCase):
    password = User.objects.make_random_password()
    user_const = dict(last_name='last', first_name='first')

    def test_get_kml_key(self):
        user = User.objects.create(username='User',
                                   email='user4@test.com',
                                   password=self.password,
                                   **self.user_const)
        token = get_kml_access_token(user)
        self.assertIsNotNone(token, 'error getting token')

    def test_reuse_existing_kml_token(self):
        user = User.objects.create(username='User',
                                   email='user4@test.com',
                                   password=self.password,
                                   **self.user_const)
        first_token = get_kml_access_token(user)
        second_token = get_kml_access_token(user)
        self.assertEqual(first_token, second_token)
