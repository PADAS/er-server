from datetime import datetime

import pytz
from django.test import TestCase

from accounts.admin import CustomUserCreationForm
from accounts.models import User


class AdditionalTestCase(TestCase):
    fixtures = ['accounts_choices.json']

    def convert_datestring_to_datetime(self, date_string):
        datetime_object = datetime.strptime(date_string, '%m/%d/%Y')
        from das_server.local_settings_template import TIME_ZONE
        datetime_object = datetime_object.astimezone(pytz.timezone(TIME_ZONE))
        return datetime_object

    def test_additional_data_fields(self):
        username = 'User'
        password = User.objects.make_random_password()
        additional_data = {
            'notes': 'Testing Notes',
            'expiry': '12/3/2018',
            'moudatesigned': '01/09/2018',
            'moutype': 'Sample MoU Type',
            'tech': ['iOS'],
            'organization': 'KWS',
        }
        form_data = {
            'first_name': 'Hugh',
            'last_name': 'Jackman',
            'email': 'hg@hollywod.com',
            'phone': '0123456789',
            'username': username,
            'password1': password,
            'password2': password
        }
        form_data = {**form_data, **additional_data}
        form = CustomUserCreationForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save()
        user = User.objects.get(username='User')

        # Update date fields from additional_data in iso format
        expiry = self.convert_datestring_to_datetime(additional_data['expiry'])
        mou_date_signed = self.convert_datestring_to_datetime(
            additional_data['moudatesigned'])
        additional_data['expiry'] = expiry.astimezone(
            pytz.timezone("UTC")).isoformat()
        additional_data['moudatesigned'] = mou_date_signed.astimezone(
            pytz.timezone("UTC")).isoformat()
        self.assertTrue(all(item in user.additional.items()
                            for item in additional_data.items()))

    def test_email_firstname_lastname_phone_as_null_or_blank(self):

        for username in ('username1', 'username2'):
            password = User.objects.make_random_password()
            additional_data = {}
            form_data = {
                'username': username,
                'password1': password,
                'password2': password
            }
            form_data = {**form_data, **additional_data}
            form = CustomUserCreationForm(data=form_data)
            self.assertTrue(form.is_valid())
            form.save()
            user = User.objects.get(username=username)
            self.assertTrue(user.email is None and user.first_name is '' and
                            user.last_name is '' and user.phone is '')
