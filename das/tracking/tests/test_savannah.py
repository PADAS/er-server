import io
from datetime import datetime, timedelta
from unittest import mock
import pytz
import json

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
import requests_mock

from core.tests import BaseAPITest, fake_get_pool
from activity.models import EventCategory, EventType
from observations.models import Source, SourceProvider, Subject, SubjectType, \
    SubjectSubType, SubjectSource
from tracking.models import SavannahPlugin, SourcePlugin
from tracking.models.savannah import SavannaClient, STObservation, STAlert
from tracking.tasks import run_source_plugin


def make_data_download(request_mock, host):
    def match_data_download(request):
        return 'data_download' in request.text

    data = json.loads("""{
        "sucess": true, "error_msg": "", "has_more_records": false,
        "records": [
            {
                "record_index": 17048927, "record_time": "8/6/2019 12:29:57",
                "time_to_fix": 0, "latitude": -3.60681,"longitude": 39.87715,
                "hdop": 0, "h_accuracy": 0, "heading": 0, "speed": 0,
                "speed_accuracy": 0, "altitude": 0, "temperature": 39,
                "initial_data": "", "battery": 3.76
             },
            {
                "record_index": 17048928, "record_time": "8/6/2019 12:30:00",
                "time_to_fix": 0, "latitude": -3.606825, "longitude": 39.87715,
                "hdop": 0, "h_accuracy": 0, "heading": 0, "speed": 0,
                "speed_accuracy": 0, "altitude": 0, "temperature": 39,
                "initial_data": "", "battery": 3.76
                },
            {
                "record_index": 17050390, "record_time": "8/6/2019 13:29:04",
                "time_to_fix": 0, "latitude": -3.606905, "longitude": 39.87722,
                "hdop": 0, "h_accuracy": 0, "heading": 0, "speed": 0,
                "speed_accuracy": 0, "altitude": 0, "temperature": 28.8,
                "initial_data": "", "battery": 3.71
                }
        ]}""")
    request_mock.register_uri('POST', host + "/savannah_data/data_request", json=data,
                              status_code=200, additional_matcher=match_data_download)


def make_exceptions_download(request_mock, host):
    def match_exceptions_download(request):
        return 'exceptions_download' in request.text

    data = json.loads("""{
    "sucess": true,
    "error_msg": "",
    "has_more_records": false,
    "records": [
        {
            "record_index": 13124338,
            "record_time": "10/4/2018 01:22:47",
            "time_to_fix": 0,
            "latitude": -1.994673,
            "longitude": 34.68869,
            "hdop": 0,
            "h_accuracy": 0,
            "heading": 0,
            "speed": 0,
            "speed_accuracy": 0,
            "altitude": 0,
            "temperature": 0,
            "initial_data": "",
            "exception_type": "IMMOBILITY ALERT",
            "battery": 0
        },
        {
            "record_index": 13124348,
            "record_time": "10/4/2018 01:42:24",
            "time_to_fix": 0,
            "latitude": -1.994668,
            "longitude": 34.68872,
            "hdop": 0,
            "h_accuracy": 0,
            "heading": 0,
            "speed": 0,
            "speed_accuracy": 0,
            "altitude": 0,
            "temperature": 0,
            "initial_data": "",
            "exception_type": "IMMOBILITY ALERT",
            "battery": 0
        },
        {
            "record_index": 13124588,
            "record_time": "10/4/2018 02:02:13",
            "time_to_fix": 0,
            "latitude": -1.994672,
            "longitude": 34.68873,
            "hdop": 0,
            "h_accuracy": 0,
            "heading": 0,
            "speed": 0,
            "speed_accuracy": 0,
            "altitude": 0,
            "temperature": 0,
            "initial_data": "",
            "exception_type": "IMMOBILITY ALERT",
            "battery": 0
        },
        {
            "record_index": 13159150,
            "record_time": "10/7/2018 00:51:24",
            "time_to_fix": 0,
            "latitude": -2.030293,
            "longitude": 34.68081,
            "hdop": 0,
            "h_accuracy": 0,
            "heading": 0,
            "speed": 0,
            "speed_accuracy": 0,
            "altitude": 0,
            "temperature": 0,
            "initial_data": "",
            "exception_type": "GPNTR",
            "battery": 0
        },
        {
            "record_index": 13159252,
            "record_time": "10/7/2018 01:11:25",
            "time_to_fix": 0,
            "latitude": -2.030326,
            "longitude": 34.68112,
            "hdop": 0,
            "h_accuracy": 0,
            "heading": 0,
            "speed": 0,
            "speed_accuracy": 0,
            "altitude": 0,
            "temperature": 0,
            "initial_data": "",
            "exception_type": "IMMOBILITY ALERT",
            "battery": 0
        },
        {
            "record_index": 13159260,
            "record_time": "10/7/2018 01:31:15",
            "time_to_fix": 0,
            "latitude": -2.030287,
            "longitude": 34.68105,
            "hdop": 0,
            "h_accuracy": 0,
            "heading": 0,
            "speed": 0,
            "speed_accuracy": 0,
            "altitude": 0,
            "temperature": 0,
            "initial_data": "",
            "exception_type": "None",
            "battery": 0
        }
    ]
}""")
    request_mock.register_uri('POST', host + "/savannah_data/data_request", json=data,
                              status_code=200, additional_matcher=match_exceptions_download)


class SavannahPluginTest(TestCase):
    api_host = "http://random"

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
            service_api_host=self.api_host)
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
    @requests_mock.Mocker()
    def test_savannah(self, request_mock):
        make_data_download(request_mock, self.api_host)
        make_exceptions_download(request_mock, self.api_host)

        plugin_class = apps.get_model('tracking', 'SavannahPlugin')

        # run plugin to fetch observations and alert type data
        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()

        self.assertEqual(len(self.henry.observations()), 8)

        # Check battery values
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
