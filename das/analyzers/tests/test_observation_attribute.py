import os
from datetime import timedelta

import pytest
from django_multitenant.utils import set_current_tenant

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from activity.constants import PRI_IMPORTANT, PRI_URGENT
from analyzers.models import ObservationAttributeAnalyzerConfig
from analyzers.observation_attribute import ObservationAttributeAnalyzer
from observations.models import Subject

from .analyzer_test_utils import generate_observations, parse_recorded_at
from .observation_attribute_test_data import TEST_OBSERVATIONS

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationAttributeAnalyzer(TestCase):

    def setUp(self):
        set_current_tenant(self.das_tenant)
        call_command("loaddata_with_tenant", "event_data_model")
        super(TestObservationAttributeAnalyzer, self).setUp()
        user_const = dict(last_name="last", first_name="first")

        self.super_user = get_user_model().objects.create_user(
            "super_admin", "superadmin@vulcan.com", "superadmin", is_superuser=True, **user_const
        )

        self.test_subject = Subject.objects.create_subject(name="Horton")
        test_observations = [parse_recorded_at(x) for x in TEST_OBSERVATIONS]
        self.test_observations = list(generate_observations(test_observations))

        oaa_config = ObservationAttributeAnalyzerConfig(
            name="Test OAA Config",
            attribute_name="battery",
            aggregation="any",
            comparator="<",
            warning_value=3.2,
            critical_value=3.0,
        )

        self.oaa = ObservationAttributeAnalyzer(config=oaa_config, subject=self.test_subject)

    def test_oaa_aggregators_any(self):

        self.oaa.config.comparator = "="
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]

        assert event.priority == PRI_IMPORTANT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.2

        self.oaa.config.warning_value = "4.1"
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

    def test_oaa_aggregators_none(self):
        self.oaa.config.aggregation = "none"
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.0
        assert event.priority == PRI_URGENT

        self.oaa.config.comparator = "<="
        self.oaa.config.critical_value = 3.2
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

    def test_oaa_aggregators_all(self):

        self.oaa.config.comparator = "="
        self.oaa.config.aggregation = "all"
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

        self.oaa.config.comparator = ">"
        self.oaa.config.warning_value = 3.5
        self.oaa.config.critical_value = 3.5
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

        self.oaa.config.critical_value = 3.0
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]

        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.0

    def test_oaa_aggregators_mean(self):

        self.oaa.config.aggregation = "mean"
        self.oaa.config.critical_value = 4
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]

        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.53

    def test_oaa_aggregators_min(self):

        self.oaa.config.aggregation = "min"
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

        self.oaa.config.comparator = "<="
        self.oaa.config.warning_value = 3.25
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_IMPORTANT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.2

    def test_oaa_aggregators_median(self):

        self.oaa.config.aggregation = "median"
        self.oaa.config.critical_value = 3.56
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.5

    def test_oaa_not_triggered(self):

        self.oaa.config.warning_value = 2
        self.oaa.config.critical_value = 1
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

    def test_adjust_oom(self):
        self.oaa.config.adjust_to_order_of_magnitude = 100
        self.oaa.config.comparator = "="
        self.oaa.config.aggregation = "mean"
        results = self.oaa.analyze(observations=self.test_observations)
        assert not results

        self.oaa.config.critical_value = 352.85714285714283
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 352.86

    def test_empty_observation_set(self):
        results = self.oaa.analyze(observations=[])
        assert not results

    def test_wrong_variable_type_in_obs_data(self):
        test_observations = [parse_recorded_at(x) for x in TEST_OBSERVATIONS]
        test_observations[0]["additional"]["battery"] = "whoa there"
        bad_observations = list(generate_observations(test_observations))
        self.oaa.config.comparator = ">"
        self.oaa.config.aggregation = "min"
        self.oaa.config.critical_value = 0
        results = self.oaa.analyze(observations=bad_observations)
        assert not results

    def test_oaa_aggregators_max(self):
        self.oaa.config.aggregation = "max"
        self.oaa.config.comparator = "<"
        self.oaa.config.critical_value = 5
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 4.0

    def test_oaa_aggregators_range(self):
        self.oaa.config.aggregation = "range"
        self.oaa.config.comparator = ">="
        self.oaa.config.critical_value = 0.5
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 0.8

    def test_oaa_aggregators_stdev(self):
        self.oaa.config.aggregation = "stdev"
        self.oaa.config.comparator = "<>"
        self.oaa.config.critical_value = 0
        results = self.oaa.analyze(observations=self.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 0.27

    def test_observations_missing_attribute(self):
        test_observations = [parse_recorded_at(x) for x in TEST_OBSERVATIONS]
        for obs in test_observations:
            obs["additional"] = {"temperature": 25.0}
        observations = list(generate_observations(test_observations))
        results = self.oaa.analyze(observations=observations)
        assert not results

    def test_quiet_period_cache(self):
        self.oaa.config.quiet_period = timedelta(hours=1)
        self.oaa.config.aggregation = "max"
        self.oaa.config.comparator = "<"
        self.oaa.config.critical_value = 5
        analyzer_key = "test_oaa_quiet_period"
        cache.delete(analyzer_key)

        results = self.oaa.analyze(observations=self.test_observations, analyzer_key=analyzer_key)
        assert len(results) == 1
        assert cache.get(analyzer_key) is not None
