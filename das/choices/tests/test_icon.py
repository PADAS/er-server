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
from utils.helpers import FileCompression
from choices.models import Choice
from choices.serializers import ChoiceIconZipSerializer
from choices.views import ChoiceZipIcon
from activity.models import EventCategory, EventType
from activity import views

User = get_user_model()

SCHEMA = """
{
   "schema":
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Other Wildlife Sighting Report (wildlife_sighting_rep)",

       "type": "object",

       "properties":
       {
            "wildlifesightingrep_species": {
                "type": "string",
                "title": "Species",
                "enum": {{enum___wildlifesightingrep_species___values}},
                "enumNames": {{enum___wildlifesightingrep_species___names}}
            },
           "wildlifesightingrep_numberanimals": {
                "type": "number",
                "title": "Count",
                "minimum":0
           },
           "wildlifesightingrep_collared": {
                "type": "string",
                "title": "Are Animals Collared",
                "enum": {{enum___yesno___values}},
                "enumNames": {{enum___yesno___names}}
           },
           "wildlifesightingrep_icons": {
                "type": "string",
                "title": "Icons",
                "enum": {{enum___wildlifesightingrep_icons___values}},
                "enumNames": {{enum___wildlifesightingrep_icons___names}}
            }

       }
   },
 "definition": [
    {
        "key":    "wildlifesightingrep_species",
        "htmlClass": "col-lg-6"
    },
    {
        "key":    "wildlifesightingrep_numberanimals",
        "htmlClass": "col-lg-6"
    },
    {
        "key":    "wildlifesightingrep_collared",
        "htmlClass": "col-lg-6"
    },
   {
        "key":    "wildlifesightingrep_icons",
        "htmlClass": "col-lg-6"
    }

 ]
}
"""


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

        choice = Choice.objects.create(model='activity.event',
                                       field='wildlifesightingrep_species',
                                       value='elephant',
                                       display='Elephant',
                                       icon='elephant_sighting_rep')

        choice = Choice.objects.create(model='activity.event',
                                       field='wildlifesightingrep_species',
                                       value='rhino',
                                       display='Rhino',
                                       icon='elephant_sighting_rep')

        choice = Choice.objects.create(model='activity.event',
                                       field='wildlifesightingrep_species',
                                       value='cheetah',
                                       display='Cheetah',
                                       icon='elephant_sighting_rep')

        choice = Choice.objects.create(model='activity.event',
                                       field='yesno',
                                       value='yes',
                                       display='Yes',
                                       icon='yes_icon')
        return choice.save()

    def test_zipfile_works(self):
        self.create_with_icon()
        url = reverse('icon-zip')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = ChoiceZipIcon.as_view()(request)

        self.assertEqual(response.status_code, 200)
        items = {name: value for name, value in response.items()}
        self.assertEqual(items['Content-Type'], 'application/zip')

    def test_choice_with_icon(self):
        self.create_with_icon()
        choices = Choice.objects.values('icon').exclude(
            Q(icon__exact='') | Q(icon__exact=None)).distinct()
        serializer = ChoiceIconZipSerializer(choices, many=True)
        zipfile_compress = FileCompression(serializer.data)
        file_path = zipfile_compress.file_paths
        self.assertTrue(os.path.exists(file_path[0]))

    def test_when_no_icon_exist(self):
        url = reverse('icon-zip')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = ChoiceZipIcon.as_view()(request)

        self.assertEqual(response.status_code, 404)

    def test_enumImages_is_inserted_if_associated_choice_has_icon(self):
        event_category = EventCategory.objects.create(
            value='monitoring', display='Monitoring', )
        event_type = EventType.objects.create(value='wildlifesightingrep_species',
                                              display='Wildlife Sighting',
                                              category=event_category,
                                              schema=SCHEMA)
        self.create_with_icon()
        request = self.factory.get(self.api_base +
                                   '/events/eventtypes/wildlifesightingrep_species')
        kwargs = {"eventtype": "wildlifesightingrep_species"}

        self.force_authenticate(request, self.user)
        response = views.EventTypeSchemaView.as_view()(request, **kwargs)

        # get values for enumImages: "maps choice value to icon value"
        enumImage_vals = dict(
            response.data['schema']['properties']['wildlifesightingrep_species']['enumImages'])
        choice_vals = dict([i for i in Choice.objects.filter(
            field='wildlifesightingrep_species').values_list('value', 'icon')])

        # get values for enumNames: "maps choice value to  display"
        enumNames_vals = dict(
            response.data['schema']['properties']['wildlifesightingrep_collared']['enumNames'])
        choice_vals_ = dict([i for i in Choice.objects.filter(
            field='yesno').values_list('value', 'display')])

        self.assertEqual(enumImage_vals, choice_vals)
        self.assertEqual(enumNames_vals, choice_vals_)
        self.assertEqual(response.status_code, 200)
