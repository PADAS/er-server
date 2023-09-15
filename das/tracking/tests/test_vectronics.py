import json
from unittest.mock import Mock, patch

import pytest

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectSubType,
    SubjectType,
)
from tracking.models import SourcePlugin, VectronicsPlugin
from tracking.tasks import execute_run_source_plugin

from .vectronic_sample_data import positions


class VectronicsPluginTest(TestCase):
    def setUp(self):
        collar_key = (
            "6484B8CA88E2B996421AB903D0B215AFAE285CAAE932F35F44815439"
            "8398CF33AC40D37D9E37CEEA9DFCBD89353C3CCF8628A4DB4523F2324A83A"
            "DA5D091FB396DAC72773ED8CE1571D5C254FABBA0FBDEE2E1883694B8D181"
            "48168B205ED5BFA96ACEC30B7B99E045B8AE145B2A83948BAECD54CAB80A7"
            "676360B74CD1DEF7DDB50293E36B1C900EA853E19F808F745D85610F68609"
            "F233E294FA1C84700A80F1C257E062CAF4B2467E518A010A59E636091BAB9"
            "05E50ED300BADF9F90440F7B85BBE14DD864BBB2F77A0A50BE5E14623D1B8"
            "FB0C2A3069207F4BFBF6CFEBC152F072D27B3CE88F844ED0197A56AF5114D"
            "E7B3BA544DB880850507FEB046684"
        )
        additional_data = {"collar_key": collar_key}
        cursor_data = {"latest_timestamp": "2018-01-01"}

        self.source_provider = SourceProvider.objects.create(
            provider_key="vectronics", display_name="Vectronics Provider"
        )
        self.source = Source.objects.create(
            provider=self.source_provider,
            manufacturer_id="1000001",
            source_type=("tracking-device", "Tracking Device"),
            additional=additional_data,
        )

        vectronic_plugin = VectronicsPlugin.objects.create(name="Vectronics", provider=self.source_provider)
        plugin_type = ContentType.objects.get(app_label="tracking", model="vectronicsplugin")
        self.source_plugin = SourcePlugin.objects.create(
            plugin_type=plugin_type, plugin_id=vectronic_plugin.id, source=self.source, cursor_data=cursor_data
        )

        subject_type, created = SubjectType.objects.get_or_create(value="wildlife")
        subject_subtype, created = SubjectSubType.objects.get_or_create(
            value="elephant", defaults=dict(subject_type=subject_type)
        )
        self.henry = Subject.objects.create(name="Henry", subject_subtype=subject_subtype)
        SubjectSource.objects.create(source=self.source, subject=self.henry)

    def not_a_est_vecronics_plugin_flow(self):
        plugin_class = apps.get_model("tracking", "VectronicsPlugin")

        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status="enabled"):
                    if sp.should_run():
                        execute_run_source_plugin(sp.id)
            else:
                plugin.execute()
        self.assertTrue(len(self.henry.observations()) > 0)

    @pytest.mark.usefixtures("tenant_settings")
    @patch("requests.get")
    def test_DAS_6875_bug(self, mock_request):
        """https://vulcan.atlassian.net/browse/DAS-6875"""
        Observation.objects.all().delete()
        mock_request.return_value = Mock(status_code=200, text=json.dumps(positions))
        cursor_data = {"latest_timestamp": "2021-06-28T10:00:39+00:00"}

        SourcePlugin.objects.update(cursor_data=cursor_data)
        plugin_class = apps.get_model("tracking", "VectronicsPlugin")

        for plugin in plugin_class.objects.all():
            if plugin.run_source_plugins:
                for sp in plugin.source_plugins.filter(status="enabled"):
                    if sp.should_run():
                        execute_run_source_plugin(sp.id, domain="zoo.com")
            else:
                plugin.execute()

        self.assertTrue(len(self.henry.observations()) == 12)
