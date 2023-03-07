import django.contrib.auth
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import QueryDict
from django.test import RequestFactory
from django.urls import reverse

from activity.admin import EventTypeAdmin
from activity.models import EventCategory, EventType
from core.tests import BaseAPITest

User = django.contrib.auth.get_user_model()

EVENT_SCHEMA_MISSING_COMMA = '\n{\n    "schema":\n        {\n            "$schema": "http://json-schema.org/draft-04/schema#",\n            "title": "EventType Test Data",\n\n            "type": "object",\n\n            "properties":\n                {\n                    "type_accident": {\n                        "type": "string",\n                        "title": "Type of accident"\n                    },\n                    "number_people_involved": {\n                        "type": "number",\n                        "title": "Number of people involved"\n                        "minimum": 0\n                    },\n                    "animals_involved": {\n                        "type": "string",\n                        "title": "Animals involved"\n                    },\n                    "hidden_field": {\n                        "type": "string",\n                        "title": "Hidden String"\n                    }\n                }\n        },\n    "definition": [\n        {\n            "key": "type_accident",\n            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "number_people_involved",\n            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "animals_involved",\n            "htmlClass": "col-lg-6"\n        }\n    ]\n}\n'

EVENT_SCHEMA_UNMATCHED_QUOTES = '\n{\n    "schema":\n        {\n            "$schema": "http://json-schema.org/draft-04/schema#",\n            "title": "EventType Test Data",\n\n            "type": "object",\n\n            "properties":\n                {\n                    "type_accident": {\n                        "type": "string",\n                        "title": "Type of accident"\n                    },\n                    "number_people_involved": {\n                        "type": "number,\n                        "title": "Number of people involved",\n                        "minimum": 0\n                    },\n                    "animals_involved": {\n                        "type": "string",\n                        "title": "Animals involved"\n                    },\n                    "hidden_field": {\n                        "type": "string",\n                        "title": "Hidden String"\n                    }\n                }\n        },\n    "definition": [\n        {\n            "key": "type_accident",\n            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "number_people_involved",\n            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "animals_involved",\n            "htmlClass": "col-lg-6"\n        }\n    ]\n}\n'

EVENT_SCHEMA_MISSING_COLON = '\n{\n    "schema": \n    {\n        "$schema": "http://json-schema.org/draft-04/schema#",\n        "title": "EventType Test Data",\n      \n        "type": "object",\n\n        "properties": \n        {\n        "type_accident": {\n            "type": "string",\n            "title": "Type of accident"\n        },\n        "number_people_involved": {\n            "type" "number",\n            "title": "Number of people involved",\n            "minimum":0\n        },\n        "animals_involved": {\n            "type": "string",\n            "title": "Animals involved"\n        },\n        "hidden_field": {\n            "type": "string",\n            "title": "Hidden String"\n        }\n    }\n  },\n  "definition": [\n    {\n        "key":     "type_accident",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":     "number_people_involved",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":     "animals_involved",\n        "htmlClass": "col-lg-6"\n    }\n  ]\n}\n'


class TestEventTypeAdmin(BaseAPITest):

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)
        self.no_perms_user = User.objects.create_user('no_perms_user',
                                                      'das_no_perms@vulcan.com',
                                                      'noperms',
                                                      **user_const)
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = EventTypeAdmin(model=EventType, admin_site=self.site)
        EventCategory.objects.create(value='test', display='TEST')

    def test_eventtype_schema_missing_comma(self):
        url = reverse('admin:activity_eventtype_add')
        event_category_id = EventCategory.objects.get(value='test')

        post_data = {'_save': 'Save',
                     'category': str(event_category_id.id),
                     'csrfmiddlewaretoken': 'gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa',
                     'default_priority': '0',
                     'default_state': 'new',
                     'display': 'Event',
                     'icon': '',
                     'ordernum': '',
                     'schema': EVENT_SCHEMA_MISSING_COMMA,
                     'value': 'test_example'}

        request = self.factory.post(url)
        self.force_authenticate(request, self.user)
        query_dict = QueryDict('', mutable=True)
        query_dict.update(post_data)

        request.POST = query_dict
        request.META['CSRF_COOKIE'] = 'gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa'
        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        response = self.admin.add_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "Expecting ',' delimiter: line 18 column 25" in messages._queued_messages[0].message)

    def test_eventtype_schema_unmatched_quotes(self):
        url = reverse('admin:activity_eventtype_add')
        event_category_id = EventCategory.objects.get(value='test')

        post_data = {'_save': 'Save',
                     'category': str(event_category_id.id),
                     'csrfmiddlewaretoken': 'gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa',
                     'default_priority': '0',
                     'default_state': 'new',
                     'display': 'Event',
                     'icon': '',
                     'ordernum': '',
                     'schema': EVENT_SCHEMA_UNMATCHED_QUOTES,
                     'value': 'test_example'}

        request = self.factory.post(url)
        self.force_authenticate(request, self.user)
        query_dict = QueryDict('', mutable=True)
        query_dict.update(post_data)

        request.POST = query_dict
        request.META['CSRF_COOKIE'] = 'gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa'
        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        response = self.admin.add_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "Invalid control character at: line 16 column 41" in messages._queued_messages[0].message)

    def test_eventtype_schema_missing_colon(self):
        url = reverse('admin:activity_eventtype_add')
        event_category_id = EventCategory.objects.get(value='test')

        post_data = {'_save': 'Save',
                     'category': str(event_category_id.id),
                     'csrfmiddlewaretoken': 'gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa',
                     'default_priority': '0',
                     'default_state': 'new',
                     'display': 'Event',
                     'icon': '',
                     'ordernum': '',
                     'schema': EVENT_SCHEMA_MISSING_COLON,
                     'value': 'test_example'}

        request = self.factory.post(url)
        self.force_authenticate(request, self.user)
        query_dict = QueryDict('', mutable=True)
        query_dict.update(post_data)

        request.POST = query_dict
        request.META['CSRF_COOKIE'] = 'gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa'
        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        response = self.admin.add_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "Expecting ':' delimiter: line 16 column 20" in messages._queued_messages[0].message)
