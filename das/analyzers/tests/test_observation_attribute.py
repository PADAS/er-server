import copy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command

from activity.constants import PRI_IMPORTANT, PRI_URGENT
from analyzers.models import ObservationAttributeAnalyzerConfig
from analyzers.observation_attribute import ObservationAttributeAnalyzer
from observations.models import Subject

from .analyzer_test_utils import generate_observations, parse_recorded_at
from .observation_attribute_test_data import TEST_OBSERVATIONS

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch"),
]


@pytest.fixture
def oaa_setup(das_tenant_monkeypatch, tenant_settings):
    """Set up tenant, event_data_model, subject, test observations, and OAA analyzer."""
    call_command("loaddata_with_tenant", "event_data_model")
    cache.clear()
    user_const = dict(last_name="last", first_name="first")

    super_user = get_user_model().objects.create_user(
        "super_admin", "superadmin@vulcan.com", "superadmin", is_superuser=True, **user_const
    )

    test_subject = Subject.objects.create_subject(name="Horton")
    test_observations = [parse_recorded_at(x) for x in TEST_OBSERVATIONS]
    test_observations = list(generate_observations(test_observations))

    oaa_config = ObservationAttributeAnalyzerConfig(
        name="Test OAA Config",
        attribute_name="battery",
        aggregation="any",
        comparator="<",
        warning_value=3.2,
        critical_value=3.0,
    )

    oaa = ObservationAttributeAnalyzer(config=oaa_config, subject=test_subject)

    return SimpleNamespace(
        super_user=super_user,
        test_subject=test_subject,
        test_observations=test_observations,
        oaa=oaa,
    )


class TestObservationAttributeAnalyzer:
    def test_oaa_aggregators_any(self, oaa_setup):
        oaa_setup.oaa.config.comparator = "="
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]

        assert event.priority == PRI_IMPORTANT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.2
        assert ed["analyzer_name"] == "Test OAA Config"

        oaa_setup.oaa.config.warning_value = "4.1"
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

    def test_oaa_aggregators_none(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "none"
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.0
        assert event.priority == PRI_URGENT

        oaa_setup.oaa.config.comparator = "<="
        oaa_setup.oaa.config.critical_value = 3.2
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

    def test_oaa_aggregators_all(self, oaa_setup):
        oaa_setup.oaa.config.comparator = "="
        oaa_setup.oaa.config.aggregation = "all"
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

        oaa_setup.oaa.config.comparator = ">"
        oaa_setup.oaa.config.warning_value = 3.5
        oaa_setup.oaa.config.critical_value = 3.5
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

        oaa_setup.oaa.config.critical_value = 3.0
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]

        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.0

    def test_oaa_aggregators_mean(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "mean"
        oaa_setup.oaa.config.critical_value = 4
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]

        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.53

    def test_oaa_aggregators_min(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "min"
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

        oaa_setup.oaa.config.comparator = "<="
        oaa_setup.oaa.config.warning_value = 3.25
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_IMPORTANT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.2

    def test_oaa_aggregators_median(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "median"
        oaa_setup.oaa.config.critical_value = 3.56
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 3.5

    def test_oaa_not_triggered(self, oaa_setup):
        oaa_setup.oaa.config.warning_value = 2
        oaa_setup.oaa.config.critical_value = 1
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

    def test_adjust_oom(self, oaa_setup):
        oaa_setup.oaa.config.adjust_to_order_of_magnitude = 100
        oaa_setup.oaa.config.comparator = "="
        oaa_setup.oaa.config.aggregation = "mean"
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert not results

        oaa_setup.oaa.config.critical_value = 352.85714285714283
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 352.86

    def test_empty_observation_set(self, oaa_setup):
        results = oaa_setup.oaa.analyze(observations=[])
        assert not results

    def test_wrong_variable_type_in_obs_data(self, oaa_setup):
        test_observations = [parse_recorded_at(copy.deepcopy(x)) for x in TEST_OBSERVATIONS]
        test_observations[0]["additional"]["battery"] = "whoa there"
        bad_observations = list(generate_observations(test_observations))
        oaa_setup.oaa.config.comparator = ">"
        oaa_setup.oaa.config.aggregation = "min"
        oaa_setup.oaa.config.critical_value = 0
        results = oaa_setup.oaa.analyze(observations=bad_observations)
        assert not results

    def test_oaa_aggregators_max(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "max"
        oaa_setup.oaa.config.comparator = "<"
        oaa_setup.oaa.config.critical_value = 5
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 4.0

    def test_oaa_aggregators_range(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "range"
        oaa_setup.oaa.config.comparator = ">="
        oaa_setup.oaa.config.critical_value = 0.5
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 0.8

    def test_oaa_aggregators_stdev(self, oaa_setup):
        oaa_setup.oaa.config.aggregation = "stdev"
        oaa_setup.oaa.config.comparator = "<>"
        oaa_setup.oaa.config.critical_value = 0
        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations)
        assert len(results) == 1
        result, event = results[0]
        assert event.priority == PRI_URGENT
        ed = event.event_details.latest("updated_at").data["event_details"]
        assert ed["evaluated_value"] == 0.27

    def test_observations_missing_attribute(self, oaa_setup):
        test_observations = [parse_recorded_at(x) for x in TEST_OBSERVATIONS]
        for obs in test_observations:
            obs["additional"] = {"temperature": 25.0}
        observations = list(generate_observations(test_observations))
        results = oaa_setup.oaa.analyze(observations=observations)
        assert not results

    def test_quiet_period_cache(self, oaa_setup):
        oaa_setup.oaa.config.quiet_period = timedelta(hours=1)
        oaa_setup.oaa.config.aggregation = "max"
        oaa_setup.oaa.config.comparator = "<"
        oaa_setup.oaa.config.critical_value = 5
        analyzer_key = "test_oaa_quiet_period"
        cache.delete(analyzer_key)

        results = oaa_setup.oaa.analyze(observations=oaa_setup.test_observations, analyzer_key=analyzer_key)
        assert len(results) == 1
        assert cache.get(analyzer_key) is not None
