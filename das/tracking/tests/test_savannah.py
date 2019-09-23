import http.client
import io
from datetime import datetime, timedelta
from unittest import mock
import pytz

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from core.tests import BaseAPITest, fake_get_pool
from activity.models import EventCategory, EventType
from observations.models import Source, SourceProvider, Subject, SubjectType, \
    SubjectSubType, SubjectSource
from tracking.models import SavannahPlugin, SourcePlugin
from tracking.models.savannah import SavannaClient, STObservation, STAlert
from tracking.tasks import run_source_plugin


# Patch function to avoid direct server call and return appropriate response
def mocked_requests_get(*args, **kwargs):
    class FakeSocket:
        def __init__(self, text, fileclass=io.BytesIO, host=None, port=None):
            if isinstance(text, str):
                text = text.encode("ascii")
            self.text = text
            self.fileclass = fileclass
            self.data = b''
            self.sendall_calls = 0
            self.host = host
            self.port = port

        def sendall(self, data):
            self.sendall_calls += 1
            self.data += data

        def makefile(self, mode, bufsize=None):
            if mode != 'r' and mode != 'rb':
                raise http.client.UnimplementedFileMode()
            return self.fileclass(self.text)

        def close(self):
            pass

    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data
    data = {
        "sucess": 'true', "error_msg": "", "has_more_records": 'false',
        "records": [
            {"record_index": 17048927, "record_time": "8\/6\/2019 12:29:57", "time_to_fix": 0, "latitude": -3.60681, "longitude": 39.87715, "hdop": 0,
                "h_accuracy": 0, "heading": 0, "speed": 0, "speed_accuracy": 0, "altitude": 0, "temperature": 39, "initial_data": "", "battery": 3.76},
            {"record_index": 17048928, "record_time": "8\/6\/2019 12:30:00", "time_to_fix": 0, "latitude": -3.606825, "longitude": 39.87715, "hdop": 0,
                "h_accuracy": 0, "heading": 0, "speed": 0, "speed_accuracy": 0, "altitude": 0, "temperature": 39, "initial_data": "", "battery": 3.76},
            {"record_index": 17050390, "record_time": "8\/6\/2019 13:29:04", "time_to_fix": 0, "latitude": -3.606905, "longitude": 39.87722, "hdop": 0,
                "h_accuracy": 0, "heading": 0, "speed": 0, "speed_accuracy": 0, "altitude": 0, "temperature": 28.8, "initial_data": "", "battery": 3.71}
        ]}
    return MockResponse(FakeSocket(data), 200)


class SavannahPluginTest(TestCase):

    def setUp(self):
        latest_timestamp = datetime.now(tz=pytz.utc) - timedelta(days=20)
        latest_timestamp = latest_timestamp.isoformat()
        cursor_data = {'latest_timestamp': latest_timestamp}

        # Create source and savannah plugin object
        # Link source and savannah plugin object using SourcePlugin
        self.source_provider = SourceProvider.objects.create(
            provider_key='savannah', display_name='Savannah')
        self.source = Source.objects.create(
            provider=self.source_provider, manufacturer_id='ST2010-3083',
            source_type=('tracking-device', 'Tracking Device'))

        savannah_plugin = SavannahPlugin.objects.create(
            name='Savannah', provider=self.source_provider,
            service_username="random", service_password="random",
            service_api_host="random")
        plugin_type = ContentType.objects.get(
            app_label='tracking', model='savannahplugin')
        self.source_plugin = SourcePlugin.objects.create(
            plugin_type=plugin_type, plugin_id=savannah_plugin.id,
            source=self.source, cursor_data=cursor_data)

        # Create Subject and link with source using SubjectSource
        subject_type, created = SubjectType.objects.get_or_create(
            value='wildlife')
        subject_subtype, created = SubjectSubType.objects.get_or_create(
            value='elephant', defaults=dict(subject_type=subject_type))
        self.henry = Subject.objects.create(
            name='Henry', subject_subtype=subject_subtype)
        SubjectSource.objects.create(source=self.source, subject=self.henry)

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    @mock.patch('tracking.models.SavannaClient.make_request')
    def xtest_savannah(self, mock_make_request):

        mock_make_request.return_value = mocked_requests_get()
        plugin_class = apps.get_model('tracking', 'SavannahPlugin')

        # run plugin to fetch observations and alert type data
        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()

        self.assertTrue(len(self.henry.observations()) == 3)

        # Check hdop & battery values
        self.assertTrue(any(observation.__dict__['additional'].get('hdop', None)
                            for observation in self.henry.observations()))
        self.assertTrue(
            any(observation.__dict__['additional'].get('battery', None)
                for observation in self.henry.observations()))

        # Check alert types immobility, immobility_all_clear in observations
        self.assertTrue(any(observation.__dict__['additional'].get(
            'device_alert', None) == 'immobility'
            for observation in self.henry.observations()))

        self.assertTrue(any(observation.__dict__['additional'].get(
            'device_alert', None) == 'immobility_all_clear'
            for observation in self.henry.observations()))

    def test_observation_parse(self):
        test_data = (['ST2010-3083', 17048927, 39.87715, -3.60681, '8/6/2019 12:29:57', 0, 0, 39, 0, 0, 3.76],
                     ['ST2010-3083', 17048927, 39.87715, -3.606825, '8/6/2019 12:30:00', 0, 0, 39, 0, 0, 3.76])
        for line in test_data:
            fix = SavannaClient.parse_line(
                STObservation, line)
            self.assertTrue(fix)

    def test_alert_parse(self):
        test_data = (['ST2010-3031', 11253, 0, 0, '7/31/2017 15:46:22', 0, 0, 0, 0, 0, 0, 'immobility', 'true'],)

        for line in test_data:
            fix = SavannaClient.parse_line(
                STAlert, line)
            self.assertTrue(fix.is_alert)
