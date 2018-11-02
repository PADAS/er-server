import ast
import os
import pytz
from datetime import datetime, timedelta

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase

from observations.models import Source, SourceProvider, Subject, SubjectType, \
    SubjectSubType, SubjectSource
from tracking.models import SourcePlugin
from tracking.models.awt import AwtPlugin, AwtClient
from tracking.tasks import run_source_plugin

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'fixtures')
TESTDATA_FILENAME = os.path.join(FIXTURE_PATH, 'awt_plugin_data.txt')


class AwtPluginTest(TestCase):
    fixtures = ['awt_plugin.json']

    def setUp(self):
        latest_timestamp = '2018-07-25T12:00:09+00:00'
        cursor_data = {'latest_timestamp': latest_timestamp}
        awt_plugin = AwtPlugin.objects.get(username='random')
        awt_client = AwtClient(username=awt_plugin.username,
                               password=awt_plugin.password,
                               host=awt_plugin.host,
                               subscription_token=awt_plugin.subscription_token)
        self.plugin_type = ContentType.objects.get(app_label='tracking',
                                                   model='awtplugin')
        self.source = Source.objects.get(manufacturer_id="2543")
        self.source_plugin = SourcePlugin.objects.create(
            plugin_type=self.plugin_type, plugin_id=awt_plugin.id,
            source=self.source, cursor_data=cursor_data)
        self.henry = Subject.objects.get(name='Henry')

        # Store data in cache
        key = 'awtplugin-observations-{username}'.format(
            username=awt_plugin.username)
        data = open(TESTDATA_FILENAME).read()
        self.data = ast.literal_eval(data)
        cache.set(key, awt_client.decrypt_response(self.data))

    def test_name(self):
        plugin_class = apps.get_model('tracking', 'AwtPlugin')
        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status='enabled'):
                    if sp.should_run():
                        run_source_plugin(sp.id)
            else:
                plugin.execute()
        source_plugin = SourcePlugin.objects.get(source=self.source)
        self.assertTrue(len(self.henry.observations()) > 0)
