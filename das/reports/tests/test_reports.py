import datetime
import uuid

from django.core.management import call_command
from django.http.request import HttpRequest
from django.test import TestCase

import reports.views as views
import utils.schema_utils as schema_utils
from accounts.models import User
from activity.models import *
from activity.serializers import EventSerializer
from reports.reports import get_conservancies, get_daily_report_data
from utils.tests_tools import is_url_resolved


class TestReportUtils(TestCase):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')
        call_command('loaddata', 'test_daily_reports')

        self.user = User.objects.create(username='reportuser', first_name='Report', last_name='User', email='reportuser@tempuri.org',
                                        password='Sko2901!kd219')

    def test_report_foo(self):
        self.assertTrue(EventType.objects.filter(value='carcass_rep').exists())

    def test_tableau_urls(self):
        assert is_url_resolved(
            "reports/tableau-dashboards/default/", views.TableauDashboard)
        assert is_url_resolved("reports/tableau-views/", views.TableauAPIView)
        assert is_url_resolved(
            f"reports/tableau-views/{uuid.uuid4()}/", views.TableauView)

    def test_render_eventdetails(self):
        edetails = {
            'beginning_of_incident': 'Monday',
            'details': 'Elephant carcass',
            'endi_of_incident': 'Monday',
            'results_and_findings': 'Trophies confiscated',
        }
        edata = {'event_type': 'carcass_rep',
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
            message = 'Event data is not valid, errors={0}'.format(ser.errors)
            logger.info(message)
            self.assertIsNotNone(None, message)

        schema = schema_utils.get_schema_renderer_method()(e.event_type.schema)

        schema_utils.validate(e, schema=schema, raise_exception=True)
        for item in schema_utils.generate_details(e, schema):
            logger.debug('Event details rendered: %s', item)

    def test_daily_report_context(self):
        edetails = {
            'beginning_of_incident': 'Monday',
            'details': 'Elephant carcass',
            'endi_of_incident': 'Monday',
            'results_and_findings': 'Trophies confiscated',
        }
        edata = {'event_type': 'carcass_rep',
                 'title': 'Test Event',
                 'priority': Event.PRI_URGENT,
                 'event_details': edetails,
                 }

        request = HttpRequest()
        request.user = User.objects.get(username='reportuser')
        ser = EventSerializer(data=edata,
                              context={'request': request})

        if ser.is_valid():
            ser.create(ser.validated_data)

        today = datetime.datetime.now(tz=datetime.timezone.utc)
        context = get_daily_report_data(
            datetime.datetime(2016, 1, 1, tzinfo=datetime.timezone.utc),         today, username=self.user.username)

        assert "unknown" in get_conservancies()
