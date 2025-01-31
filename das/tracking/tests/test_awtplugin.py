import ast
import logging
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import celery.exceptions
import pytest
from django_multitenant.utils import set_current_tenant

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase

from core.models import DASTenant
from core.tests import fake_get_pool
from observations.models import Source, Subject
from tracking.models import SourcePlugin
from tracking.models.awt import AwtClient, AwtPlugin
from tracking.tasks import DasPluginSourceRetryError, run_source_plugin

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
TESTDATA_FILENAME = os.path.join(FIXTURE_PATH, "awt_plugin_data.txt")

logger = logging.getLogger(__name__)


class AwtPluginTest(TestCase):
    def setUp(self):
        tenant = DASTenant.objects.first()
        set_current_tenant(tenant)

        call_command("loaddata_with_tenant", "awt_plugin.json")
        latest_timestamp = "2018-07-25T12:00:09+00:00"
        cursor_data = {"latest_timestamp": latest_timestamp}
        awt_plugin = AwtPlugin.objects.get(username="random")
        self.awt_client = AwtClient(
            username=awt_plugin.username,
            password=awt_plugin.password,
            host=awt_plugin.host,
            subscription_token=awt_plugin.subscription_token,
        )
        self.plugin_type = ContentType.objects.get(app_label="tracking", model="awtplugin")
        self.source = Source.objects.get(manufacturer_id="2543")
        self.source_plugin = SourcePlugin.objects.create(
            plugin_type=self.plugin_type, plugin_id=awt_plugin.id, source=self.source, cursor_data=cursor_data
        )
        self.henry = Subject.objects.get(name="Henry")

        # Store data in cache
        data = open(TESTDATA_FILENAME).read()
        self.data = ast.literal_eval(data)

    @patch("das_server.pubsub.get_pool", fake_get_pool)
    @pytest.mark.usefixtures("tenant_settings")
    def test_name(self):
        with patch("tracking.models.awt.AwtClient.fetch_data") as mock_fetch_data:
            mock_fetch_data.return_value = self.awt_client.decrypt_response(self.data)
            plugin_class = apps.get_model("tracking", "AwtPlugin")
            for plugin in plugin_class.objects.all():
                if plugin.run_source_plugins:
                    for sp in plugin.source_plugins.filter(status="enabled"):
                        if sp.should_run():
                            run_source_plugin.apply(args=(sp.id,))
                else:
                    plugin.execute()

        source_plugin = SourcePlugin.objects.get(source=self.source)
        self.assertTrue(len(self.henry.observations()) > 0)

    @patch("das_server.pubsub.get_pool", fake_get_pool)
    @pytest.mark.usefixtures("tenant_settings")
    def test_retry_lock(self):
        def cache_get(key=""):
            ttl = datetime.now(tz=timezone.utc) + timedelta(seconds=100)
            logger.info(f"requesting cache key {key}")
            if "use_policy" in key:
                return ttl.isoformat()

        with patch("tracking.models.awt.cache") as mock_cache:
            mock_cache.get = cache_get
            sp = SourcePlugin.objects.get(source=self.source)
            with self.assertRaises(DasPluginSourceRetryError):
                sp.execute()

            result = run_source_plugin.apply(args=(sp.id,))
            assert result.state == celery.states.RETRY

    def test_awt_temp_and_batt_saved_as_floats(self):
        test_data = {
            "unit_id": "AWTIMCVAP256",
            "tag_id": 1081026,
            "alarms": {
                "Track Mode": False,
                "Battery": False,
                "Geofence": False,
                "Coverage": True,
                "Memory": False,
                "CBit": False,
                "Movement": "Unknown",
                "Tamperfoil": False,
            },
            "batt": 6,
            "temperature": "Unknown",
            "timestamp": 1591663622,
            "lat": -1.3824166666666666,
            "lon": 35.487966666666665,
            "dop": 0,
            "speed": 0,
            "accelerometer": {"X": "Unknown", "Y": "Unknown", "Z": "Unknown"},
            "log_interval": "Off",
        }

        plugin = AwtPlugin()
        observation = plugin._transform_to_observation(self.source, test_data)
        self.assertTrue(isinstance(observation.additional.get("temperature"), float))
        self.assertTrue(isinstance(observation.additional.get("batt"), float))
