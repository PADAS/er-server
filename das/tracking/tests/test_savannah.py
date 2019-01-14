import http.client
import io
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import patch

import pytz
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

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
        def __init__(self):
            self.url = None

        def request(self, method, url, body=None, headers={}, *,
                    encode_chunked=False):
            self.url = url
            return url

        def getresponse(self):
            # If url is get_data, return Observation or return Alert data
            if self.url == "/savannah/get_data.asp":
                body = 'HTTP/1.1 200 Ok\r\n\r\nST2010-3031,36.78418,-1.24359,' \
                       '7/5/2018 3:38:03 PM,0,0,21.2,0,17,55'
            else:
                body = 'HTTP/1.1 200 Ok\r\n\r\nST2010-1231,' \
                       '37.51645,0.70056,12/19/2016 2:10:12 AM,0.02,233,,988,' \
                       'Immobility Alert\r\nST2010-1231,37.3583,0.63072,' \
                       '1/6/2017 11:38:25 PM,0.04,266,,983,None\r\n' \
                       'ST2010-3031,36.78418,-1.24359,7/5/2018 3:38:03 PM,0,' \
                       '0,21.2,0,Immobility Alert'
            sock = FakeSocket(body)
            resp = http.client.HTTPResponse(sock)
            resp.status = 200
            resp.begin()
            return resp

    return MockResponse()


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

    @mock.patch('http.client.HTTPConnection', side_effect=mocked_requests_get)
    def test_savannah(self, *args, **kwargs):
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
        test_data = (b'ST2010-3034,31.38607,-24.73696,11/30/2018 9:00:36 PM,0,0,18.1,0\r\n',
                     b'ST2010-3034,31.38607,-24.73696,11/30/2018 9:00:36 PM,0,0,18.1,0,44,55\r\n',
                     )

        for line in test_data:
            fix = SavannaClient.parse_line(
                STObservation, line.decode('utf-8').strip())
            self.assertTrue(fix)

    def test_alert_parse(self):
        test_data = (b'ST2010-1231,37.51645,0.70056,12/19/2016 2:10:12 AM,0.02,233,,988,44,55,Immobility Alert,true\r\n',
                     b'ST2010-1231,37.51645,0.70056,12/19/2016 2:10:12 AM,0.02,233,,988,,,Immobility Alert,true\r\n',
                     )

        for line in test_data:
            fix = SavannaClient.parse_line(
                STAlert, line.decode('utf-8').strip())
            self.assertTrue(fix.is_alert)
