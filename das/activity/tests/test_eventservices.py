import logging

import urllib.parse
from datetime import datetime, timedelta
import pytz

from django.http.request import HttpRequest
import django.contrib.auth
from django.test import TestCase
from django.core.management import call_command
from activity.models import Event
from activity.alerting.legacymailer import build_deep_link_for_subject
from activity.serializers import EventSerializer

from observations.models import Subject

logger = logging.getLogger(__name__)

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

ET_SECURITY = 'carcass_rep'
ET_MONITORING = 'wildlife_sighting_rep'
ET_LOGISTICS = 'all_posts'


class TestEventServices(TestCase):

    @classmethod
    def setUpClass(cls):

        super().setUpClass()
        call_command('loaddata', 'initial_eventdata')

        cls.plain_user = User.objects.create_user(
            'someusername', 'someuser@tempuri.org',
            'AbODI#@!018234', first_name='Some', last_name='Name')

    def test_event_with_related_subject(self):
        '''
        Test EventRelatedSubject model.
        '''
        elephant = Subject.objects.create(name='Relative Subject No. 1')

        event_data = dict(
            title='Sample Event No. 3',
            time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_ANALYZER,
            event_type='immobility',
            priority=Event.PRI_REFERENCE,
            location={'longitude': 36.8, 'latitude': 1.55},
            event_details={'message': 'sample event'},
            related_subjects=[{'id': elephant.id, }, ]
        )

        request = HttpRequest()
        request.user = self.plain_user

        event_serializer = EventSerializer(
            data=event_data, context={'request': request})

        self.assertTrue(event_serializer.is_valid(), 'Event data is not valid')
        event = event_serializer.create(event_serializer.validated_data)

        event = Event.objects.get(id=event.id)
        self.assertEqual(event.related_subjects.count(), 1)

    def test_event_mailer_data(self):

        elephant = Subject.objects.create(name='Relative Subject No. 1')

        event_data = dict(
            title='Sample Event No. 3',
            time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_ANALYZER,
            event_type='immobility',
            priority=Event.PRI_REFERENCE,
            location={'longitude': 36.8, 'latitude': 1.55},
            event_details={'message': 'sample event'},
            related_subjects=[{'id': elephant.id, }, ]
        )

        request = HttpRequest()
        request.user = self.plain_user

        event_serializer = EventSerializer(
            data=event_data, context={'request': request})

        self.assertTrue(event_serializer.is_valid(), 'Event data is not valid')
        event = event_serializer.create(event_serializer.validated_data)

        event = Event.objects.get(id=event.id)

        # Request a link
        link = build_deep_link_for_subject(event, elephant,)

        # Validate the link's schema
        sch, data = link.split('?')
        self.assertEqual(sch, 'steta://')

        # Decompose the link's query-string and validate it matches the even we
        # created.
        data = dict((a.split('=')) for a in data.split('&'))
        data = dict((x, urllib.parse.unquote(y)) for x, y in data.items())

        self.assertEqual(data['lat'], str(event_data['location']['latitude']))
        self.assertEqual(data['lon'], str(event_data['location']['longitude']))
        self.assertEqual(data['name'], str(elephant.name))
        self.assertEqual(data['t'], event.time.strftime('%Y-%m-%dT%H:%M:%S'))
        self.assertEqual(data['id'], str(elephant.id))
        self.assertEqual(data['event'], 'immobility')
