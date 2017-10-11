from django.test import TestCase
from django.contrib.auth.models import Permission
from accounts.models import PermissionSet, User
from observations.models import SubjectGroup, Subject
from activity.models import *
from django.core.management import call_command
import utils.schema_utils as schema_utils
from activity.serializers import EventSerializer
from django.http.request import HttpRequest


class TestReportUtils(TestCase):

    fixtures = ['standard-eventtyps.yaml', ]

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        User.objects.create(username='reportuser', first_name='Report', last_name='User', email='reportuser@tempuri.org',
                            password='Sko2901!kd219')

    def test_report_foo(self):
        self.assertTrue(EventType.objects.filter(value='carcass').exists())

    def test_render_eventdetails(self):
        edetails = {
            'beginning_of_incident': 'Monday',
            'details': 'Elephant carcass',
            'endi_of_incident': 'Monday',
            'results_and_findings': 'Trophies confiscated',
        }
        edata = {'event_type': 'carcass',
                 'title': 'Test Event',
                 'priority': Event.PRI_URGENT,
                 'event_details': edetails,
                 }

        request = HttpRequest()
        request.user = User.objects.get(username='reportuser')
        ser = EventSerializer(data=edata,
                              context={'request': request})

        if ser.is_valid():
            e = ser.create(ser.validated_data)
            self.assertTrue(e.id is not None)
        else:
            print(ser.errors)

        schema = schema_utils.schema_renderer()(e.event_type.schema)

        schema_utils.validate(e, schema=schema, raise_exception=True)
        for item in schema_utils.generate_details(e, schema):
            print(item)
