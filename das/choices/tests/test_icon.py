import os
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.db.models import Q

from core.tests import BaseAPITest
from accounts.models import PermissionSet
from utils.helpers import ZipFileCompression
from choices.models import Choice
from choices.serializers import ChoiceIconZipSerializer
from choices.views import ChoiceIconZip

User = get_user_model()


class TestChoice(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.user = User.objects.create_user('all_perms_user',
                                             'das_all_perms@vulcan.com',
                                             'all_perms_user',
                                             last_name='Last',
                                             first_name='First')

    def create_with_icon(self):
        choice = Choice.objects.create(model='activity.eventtype',
                                       field='wildlifesighting_icon',
                                       value='elephant',
                                       display='Elephant',
                                       icon='elephant_sighting_rep')
        return choice.save()

    def test_zipfile_works(self):
        self.create_with_icon()
        url = reverse('icon-zip')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = ChoiceIconZip.as_view()(request)

        self.assertEqual(response.status_code, 200)
        items = {name: value for name, value in response.items()}
        self.assertEqual(items['Content-Type'], 'application/zip')

    def test_choice_with_icon(self):
        self.create_with_icon()
        choices = Choice.objects.values('icon').exclude(
            Q(icon__exact='') | Q(icon__exact=None)).distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        zipfile_compress = ZipFileCompression(serializer.data)
        file_path = zipfile_compress.check_file_type()
        self.assertTrue(os.path.exists(file_path[0]))

    def test_message_when_zipfile(self):
        url = reverse('icon-zip')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = ChoiceIconZip.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, "No icon(s) for choices found")

