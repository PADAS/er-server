from datetime import datetime

import pytz
from django.test import TestCase

from accounts.admin import CustomUserCreationForm
from accounts.models import User


class AdditionalTestCase(TestCase):
    fixtures = ['accounts_choices.json']

    def test_additional_data_fields(self):
        username = 'User'
        password = User.objects.make_random_password()
        additional_data = {
            'notes': 'Testing Notes',
            'expiry': '12/3/2018',
            'mou_date_signed': '01/09/2018',
            'mou_type': 'Sample MoU Type',
            'tech': ['iOS'],
            'organization': ['KWS'],
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
        expiry = datetime.strptime(additional_data['expiry'], '%m/%d/%Y')
        mou_date_signed = datetime.strptime(additional_data['mou_date_signed'],
                                            '%m/%d/%Y')
        additional_data['expiry'] = pytz.utc.localize(expiry).isoformat()
        additional_data['mou_date_signed'] = pytz.utc.localize(
            mou_date_signed).isoformat()
        self.assertTrue(all(item in user.additional.items()
                            for item in additional_data.items()))
