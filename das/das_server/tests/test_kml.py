from django.test import TestCase

from accounts.models import User


class UserModelTest(TestCase):
    password = User.objects.make_random_password()
    user_const = dict(last_name='last', first_name='first')

    def test_get_kml_key(self):
        user = User.objects.create(username='User',
                                   email='user4@test.com',
                                   password=self.password,
                                   **self.user_const)
        token = user.get_kml_access_token()
        self.assertIsNotNone(token, 'error getting token')

    def test_reuse_existing_kml_token(self):
        user = User.objects.create(username='User',
                                   email='user4@test.com',
                                   password=self.password,
                                   **self.user_const)
        first_token = user.get_kml_access_token()
        second_token = user.get_kml_access_token()
        self.assertEqual(first_token, second_token)
